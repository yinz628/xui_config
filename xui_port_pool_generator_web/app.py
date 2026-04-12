import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from xui_port_pool_generator.pipeline import run_pipeline

from .artifact_sync import refresh_snapshot_and_invalidate_generated
from .mapping_store import (
    load_mapping_raw,
    load_report,
    load_report_summary,
    load_state,
    load_state_groups,
    save_mapping_raw,
)
from .source_tools import (
    import_node_payload_source,
    import_yaml_source,
    inspect_source_url,
    parse_node_payload,
)
from .runtime_config import (
    load_runtime_file_metadata,
    validate_mapping_yaml,
    validate_template_json,
)
from .rule_builder import (
    build_region_index,
    filter_snapshot_for_group,
    load_snapshot,
    resolve_snapshot_path,
)


ISSUE_REASON_LABELS = {
    "group_not_matched": "未命中任何分组规则",
    "group_capacity_exceeded": "分组端口池已满",
    "parse_error_invalid_subscription_payload": "订阅内容不是可识别的 Clash 配置",
    "parse_error_invalid_port": "节点端口字段无效",
    "parse_error_missing_port": "节点缺少端口字段",
    "parse_error_missing_name": "节点缺少名称字段",
    "parse_error_missing_type": "节点缺少类型字段",
    "parse_error_missing_server": "节点缺少服务器字段",
    "inferred_obfs": "采用了推断的 obfs 转换",
}

PLACEHOLDER_VALUES = {
    "",
    "admin",
    "change-me",
    "replace-this-secret",
    "__CHANGE_ME__",
    "__GENERATE_A_LONG_RANDOM_SECRET__",
}


@dataclass(frozen=True)
class AppSettings:
    base_dir: Path
    mapping_path: Path
    template_path: Path
    workdir: Path
    admin_password: str
    session_secret: str


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or load_settings_from_env()
    templates = Jinja2Templates(
        directory=str(Path(__file__).with_name("templates"))
    )

    app = FastAPI(title="X-UI 中文控制台")
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.state.settings = settings
    app.state.templates = templates

    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard", status_code=302)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": None},
        )

    @app.post("/login", response_class=HTMLResponse)
    async def login_submit(request: Request, password: str = Form(...)):
        if password != settings.admin_password:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"request": request, "error": "密码错误"},
                status_code=401,
            )
        request.session["authenticated"] = True
        return RedirectResponse(url="/dashboard", status_code=303)

    @app.post("/logout")
    async def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect

        mapping = load_mapping_raw(settings.mapping_path)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            build_dashboard_context(
                request,
                mapping,
                saved=request.query_params.get("saved") == "1",
            ),
        )

    @app.post("/dashboard/sources/save")
    async def dashboard_sources_save(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        _save_sources_from_request(await request.form(), settings)
        refresh_snapshot_and_invalidate_generated(
            settings.mapping_path,
            settings.workdir,
        )
        return RedirectResponse(url="/dashboard?saved=1", status_code=303)

    @app.post("/dashboard/sources/save-and-generate")
    async def dashboard_sources_save_and_generate(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        _save_sources_from_request(await request.form(), settings)
        try:
            run_pipeline(settings.mapping_path, settings.template_path, settings.workdir)
        except Exception as exc:  # noqa: BLE001
            mapping = load_mapping_raw(settings.mapping_path)
            return templates.TemplateResponse(
                request,
                "dashboard.html",
                build_dashboard_context(
                    request,
                    mapping,
                    generate_error=f"生成失败：{exc}",
                ),
                status_code=200,
            )
        return RedirectResponse(url="/generate?generated=1", status_code=303)

    @app.get("/sources", response_class=HTMLResponse)
    async def sources_page(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        return templates.TemplateResponse(
            request,
            "sources.html",
            build_sources_context(
                request,
                mapping,
                saved=request.query_params.get("saved") == "1",
            ),
        )

    @app.post("/sources/save", response_class=HTMLResponse)
    async def sources_save(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        _save_sources_from_request(await request.form(), settings)
        refresh_snapshot_and_invalidate_generated(
            settings.mapping_path,
            settings.workdir,
        )
        return RedirectResponse(url="/sources?saved=1", status_code=303)

    @app.post("/sources/delete")
    async def sources_delete(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        form = await request.form()
        index = int(form.get("delete_index", 0))
        raw = load_mapping_raw(settings.mapping_path)
        sources = list(raw.get("sources", []))
        if 0 <= index < len(sources):
            sources.pop(index)
        raw["sources"] = sources
        save_mapping_raw(settings.mapping_path, raw)
        refresh_snapshot_and_invalidate_generated(
            settings.mapping_path,
            settings.workdir,
        )
        return RedirectResponse(url="/sources?saved=1", status_code=303)

    @app.post("/sources/check", response_class=HTMLResponse)
    async def sources_check(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        form = await request.form()
        mapping = _mapping_from_sources_form(form, settings)
        index = int(form.get("check_index", 0))
        try:
            source = _source_from_form_index(form, index)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "sources.html",
                build_sources_context(
                    request,
                    mapping,
                    import_error=str(exc),
                ),
                status_code=400,
            )
        check_result = inspect_source_url(source["url"], source["format"])
        return templates.TemplateResponse(
            request,
            "sources.html",
            build_sources_context(
                request,
                mapping,
                check_result=check_result,
                check_index=index,
            ),
        )

    @app.post("/sources/import-yaml", response_class=HTMLResponse)
    async def sources_import_yaml(
        request: Request,
        source_name: str = Form(""),
        yaml_file: UploadFile = File(...),
    ):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        raw = load_mapping_raw(settings.mapping_path)
        try:
            imported = import_yaml_source(
                yaml_file,
                settings.mapping_path.parent,
                {item["id"] for item in raw.get("sources", [])},
                source_name=source_name,
            )
            raw.setdefault("sources", []).append(imported["source"])
            save_mapping_raw(settings.mapping_path, raw)
            refresh_snapshot_and_invalidate_generated(
                settings.mapping_path,
                settings.workdir,
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "sources.html",
                build_sources_context(
                    request,
                    raw,
                    import_error=str(exc),
                ),
                status_code=400,
            )

        mapping = load_mapping_raw(settings.mapping_path)
        return templates.TemplateResponse(
            request,
            "sources.html",
            build_sources_context(
                request,
                mapping,
                import_message=(
                    f"导入成功：新增 {imported['source']['id']}，"
                    f"识别到 {imported['node_count']} 个节点，并已同步到分组规则。"
                ),
                node_preview=imported["node_preview"],
            ),
        )

    @app.post("/sources/inspect-nodes", response_class=HTMLResponse)
    async def sources_inspect_nodes(
        request: Request,
        node_payload: str = Form(...),
        source_name: str = Form(""),
    ):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        raw = load_mapping_raw(settings.mapping_path)
        try:
            imported = import_node_payload_source(
                node_payload,
                settings.mapping_path.parent,
                {item["id"] for item in raw.get("sources", [])},
                source_name=source_name,
            )
            raw.setdefault("sources", []).append(imported["source"])
            save_mapping_raw(settings.mapping_path, raw)
            refresh_snapshot_and_invalidate_generated(
                settings.mapping_path,
                settings.workdir,
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "sources.html",
                build_sources_context(
                    request,
                    raw,
                    import_error=str(exc),
                    node_preview=parse_node_payload(node_payload),
                ),
                status_code=400,
            )

        mapping = load_mapping_raw(settings.mapping_path)
        return templates.TemplateResponse(
            request,
            "sources.html",
            build_sources_context(
                request,
                mapping,
                import_message=(
                    f"识别并添加成功：新增 {imported['source']['id']}，"
                    f"识别到 {imported['node_count']} 个节点，并已同步到分组规则。"
                ),
                node_preview=imported["node_preview"],
            ),
        )

    @app.get("/groups", response_class=HTMLResponse)
    async def groups_page(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        return templates.TemplateResponse(
            request,
            "groups.html",
            build_groups_context(
                request,
                mapping,
                saved=request.query_params.get("saved") == "1",
            ),
        )

    @app.post("/groups/save", response_class=HTMLResponse)
    async def groups_save(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        form = await request.form()
        raw = load_mapping_raw(settings.mapping_path)
        try:
            raw = _mapping_from_groups_form(form, settings)
            save_mapping_raw(settings.mapping_path, raw)
            refresh_snapshot_and_invalidate_generated(
                settings.mapping_path,
                settings.workdir,
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "groups.html",
                build_groups_context(
                    request,
                    raw,
                    error=str(exc),
                ),
                status_code=400,
            )
        return RedirectResponse(url="/groups?saved=1", status_code=303)

    @app.post("/groups/builder/open")
    async def groups_builder_open(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        form = await request.form()
        raw = load_mapping_raw(settings.mapping_path)
        try:
            raw = _mapping_from_groups_form(form, settings)
            builder_index = int(form.get("builder_index", 0))
            group_names = form.getlist("group_name")
            if not 0 <= builder_index < len(group_names):
                raise ValueError("未找到要打开的分组。")
            group_name = group_names[builder_index].strip()
            if not group_name:
                raise ValueError("请先填写分组名称，再打开规则生成器。")
            save_mapping_raw(settings.mapping_path, raw)
            refresh_snapshot_and_invalidate_generated(
                settings.mapping_path,
                settings.workdir,
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "groups.html",
                build_groups_context(
                    request,
                    raw,
                    error=str(exc),
                ),
                status_code=400,
            )
        return RedirectResponse(
            url=f"/groups/{group_name}/builder#builder-panel",
            status_code=303,
        )

    @app.get("/runtime-config", response_class=HTMLResponse)
    async def runtime_config_page(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping_meta = load_runtime_file_metadata(settings.mapping_path)
        template_meta = load_runtime_file_metadata(settings.template_path)
        example_mapping_meta = load_runtime_file_metadata(settings.mapping_path.parent / "mapping.vps.example.yaml")
        example_template_meta = load_runtime_file_metadata(settings.template_path.parent / "config.json.example")
        return templates.TemplateResponse(
            request,
            "runtime_config.html",
            {
                "request": request,
                "mapping_meta": mapping_meta,
                "template_meta": template_meta,
                "example_mapping_meta": example_mapping_meta,
                "example_template_meta": example_template_meta,
                "mapping_message": None,
                "template_message": None,
                "mapping_error": None,
                "template_error": None,
            },
        )

    @app.post("/runtime-config/save-mapping", response_class=HTMLResponse)
    async def runtime_config_save_mapping(request: Request, mapping_text: str = Form(...)):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        try:
            validate_mapping_yaml(mapping_text)
            settings.mapping_path.write_text(mapping_text + "\n", encoding="utf-8")
            mapping_message = "运行态 mapping.yaml 已保存"
            mapping_error = None
        except Exception as exc:  # noqa: BLE001
            mapping_message = None
            mapping_error = str(exc)
            status_code = 400
        else:
            status_code = 200
        return templates.TemplateResponse(
            request,
            "runtime_config.html",
            {
                "request": request,
                "mapping_meta": load_runtime_file_metadata(settings.mapping_path),
                "template_meta": load_runtime_file_metadata(settings.template_path),
                "example_mapping_meta": load_runtime_file_metadata(settings.mapping_path.parent / "mapping.vps.example.yaml"),
                "example_template_meta": load_runtime_file_metadata(settings.template_path.parent / "config.json.example"),
                "mapping_message": mapping_message,
                "template_message": None,
                "mapping_error": mapping_error,
                "template_error": None,
            },
            status_code=status_code,
        )

    @app.post("/runtime-config/save-template", response_class=HTMLResponse)
    async def runtime_config_save_template(request: Request, template_text: str = Form(...)):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        try:
            validate_template_json(template_text)
            settings.template_path.write_text(template_text + "\n", encoding="utf-8")
            template_message = "运行态 config.json 已保存"
            template_error = None
        except Exception as exc:  # noqa: BLE001
            template_message = None
            template_error = str(exc)
            status_code = 400
        else:
            status_code = 200
        return templates.TemplateResponse(
            request,
            "runtime_config.html",
            {
                "request": request,
                "mapping_meta": load_runtime_file_metadata(settings.mapping_path),
                "template_meta": load_runtime_file_metadata(settings.template_path),
                "example_mapping_meta": load_runtime_file_metadata(settings.mapping_path.parent / "mapping.vps.example.yaml"),
                "example_template_meta": load_runtime_file_metadata(settings.template_path.parent / "config.json.example"),
                "mapping_message": None,
                "template_message": template_message,
                "mapping_error": None,
                "template_error": template_error,
            },
            status_code=status_code,
        )

    @app.post("/runtime-config/upload-mapping", response_class=HTMLResponse)
    async def runtime_config_upload_mapping(request: Request, mapping_file: UploadFile = File(...)):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        text = (await mapping_file.read()).decode("utf-8")
        try:
            validate_mapping_yaml(text)
            settings.mapping_path.write_text(text + "\n", encoding="utf-8")
            mapping_message = "运行态 mapping.yaml 已上传"
            mapping_error = None
            status_code = 200
        except Exception as exc:  # noqa: BLE001
            mapping_message = None
            mapping_error = str(exc)
            status_code = 400
        return templates.TemplateResponse(
            request,
            "runtime_config.html",
            {
                "request": request,
                "mapping_meta": load_runtime_file_metadata(settings.mapping_path),
                "template_meta": load_runtime_file_metadata(settings.template_path),
                "example_mapping_meta": load_runtime_file_metadata(settings.mapping_path.parent / "mapping.vps.example.yaml"),
                "example_template_meta": load_runtime_file_metadata(settings.template_path.parent / "config.json.example"),
                "mapping_message": mapping_message,
                "template_message": None,
                "mapping_error": mapping_error,
                "template_error": None,
            },
            status_code=status_code,
        )

    @app.post("/runtime-config/upload-template", response_class=HTMLResponse)
    async def runtime_config_upload_template(request: Request, template_file: UploadFile = File(...)):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        text = (await template_file.read()).decode("utf-8")
        try:
            validate_template_json(text)
            settings.template_path.write_text(text + "\n", encoding="utf-8")
            template_message = "运行态 config.json 已上传"
            template_error = None
            status_code = 200
        except Exception as exc:  # noqa: BLE001
            template_message = None
            template_error = str(exc)
            status_code = 400
        return templates.TemplateResponse(
            request,
            "runtime_config.html",
            {
                "request": request,
                "mapping_meta": load_runtime_file_metadata(settings.mapping_path),
                "template_meta": load_runtime_file_metadata(settings.template_path),
                "example_mapping_meta": load_runtime_file_metadata(settings.mapping_path.parent / "mapping.vps.example.yaml"),
                "example_template_meta": load_runtime_file_metadata(settings.template_path.parent / "config.json.example"),
                "mapping_message": None,
                "template_message": template_message,
                "mapping_error": None,
                "template_error": template_error,
            },
            status_code=status_code,
        )

    @app.post("/groups/delete")
    async def groups_delete(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        form = await request.form()
        index = int(form.get("delete_index", 0))
        raw = load_mapping_raw(settings.mapping_path)
        groups = list(raw.get("groups", []))
        if 0 <= index < len(groups):
            groups.pop(index)
        raw["groups"] = groups
        save_mapping_raw(settings.mapping_path, raw)
        refresh_snapshot_and_invalidate_generated(
            settings.mapping_path,
            settings.workdir,
        )
        return RedirectResponse(url="/groups?saved=1", status_code=303)

    @app.get("/groups/{group_name}/builder", response_class=HTMLResponse)
    async def groups_builder(request: Request, group_name: str):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        snapshot_path = resolve_snapshot_path(settings.mapping_path, settings.workdir)
        snapshot = load_snapshot(snapshot_path)
        group = next((item for item in mapping.get("groups", []) if item.get("name") == group_name), None)
        return templates.TemplateResponse(
            request,
            "groups.html",
            {
                "request": request,
                "mapping": mapping,
                "saved": False,
                "error": None,
                "builder_group": group,
                "builder_regions": build_region_index(snapshot),
                "builder_nodes": filter_snapshot_for_group(snapshot, group_name),
            },
        )

    @app.post("/groups/{group_name}/builder/save")
    async def groups_builder_save(request: Request, group_name: str):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        form = await request.form()
        raw = load_mapping_raw(settings.mapping_path)
        for item in raw.get("groups", []):
            if item.get("name") != group_name:
                continue
            item["include_regions"] = form.getlist("include_regions")
            item["exclude_regions"] = form.getlist("exclude_regions")
            item["manual_include_nodes"] = form.getlist("manual_include_nodes")
            item["manual_exclude_nodes"] = form.getlist("manual_exclude_nodes")
            break
        save_mapping_raw(settings.mapping_path, raw)
        refresh_snapshot_and_invalidate_generated(
            settings.mapping_path,
            settings.workdir,
        )
        return RedirectResponse(
            url=f"/groups/{group_name}/builder#builder-panel",
            status_code=303,
        )

    @app.get("/generate", response_class=HTMLResponse)
    async def generate_page(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        report = load_report(resolve_runtime_path(settings.workdir, mapping, "report_path"))
        return templates.TemplateResponse(
            request,
            "generate.html",
            {
                "request": request,
                "summary": report.get("summary", {}),
                "generated": request.query_params.get("generated") == "1",
                "artifacts": build_artifact_paths(settings.workdir, mapping),
            },
        )

    @app.post("/generate/run")
    async def generate_run(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        run_pipeline(settings.mapping_path, settings.template_path, settings.workdir)
        return RedirectResponse(url="/generate?generated=1", status_code=303)

    @app.get("/reports", response_class=HTMLResponse)
    async def reports_page(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        report = load_report(resolve_runtime_path(settings.workdir, mapping, "report_path"))
        state = load_state(resolve_runtime_path(settings.workdir, mapping, "state_path"))
        state_rows = [
            {
                "group_name": group_name,
                "binding_count": len(bindings),
                "ports": sorted(bindings.keys(), key=int),
            }
            for group_name, bindings in state.get("groups", {}).items()
        ]
        return templates.TemplateResponse(
            request,
            "reports.html",
            {
                "request": request,
                "report": report,
                "state": state,
                "state_rows": state_rows,
                "issue_reason_labels": ISSUE_REASON_LABELS,
                "describe_issue_reason": describe_issue_reason,
            },
        )

    @app.get("/downloads/config")
    async def download_config(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        path = resolve_runtime_path(settings.workdir, mapping, "output_path")
        return FileResponse(path, filename=path.name, media_type="application/json")

    @app.get("/downloads/report")
    async def download_report(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        path = resolve_runtime_path(settings.workdir, mapping, "report_path")
        return FileResponse(path, filename=path.name, media_type="application/json")

    @app.get("/downloads/state")
    async def download_state(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        path = resolve_runtime_path(settings.workdir, mapping, "state_path")
        return FileResponse(path, filename=path.name, media_type="application/json")

    return app


def ensure_authenticated(request: Request) -> RedirectResponse | None:
    if request.session.get("authenticated"):
        return None
    return RedirectResponse(url="/login", status_code=302)


def load_settings_from_env() -> AppSettings:
    base_dir = Path(os.getenv("WEB_BASE_DIR", Path(__file__).resolve().parents[1]))
    admin_password = os.getenv("WEB_ADMIN_PASSWORD", "").strip()
    session_secret = os.getenv("WEB_SESSION_SECRET", "").strip()

    if admin_password in PLACEHOLDER_VALUES:
        raise RuntimeError("WEB_ADMIN_PASSWORD must be set to a non-placeholder value.")
    if session_secret in PLACEHOLDER_VALUES:
        raise RuntimeError("WEB_SESSION_SECRET must be set to a non-placeholder value.")

    return AppSettings(
        base_dir=base_dir,
        mapping_path=Path(os.getenv("WEB_MAPPING_PATH", base_dir / "mapping.yaml")),
        template_path=Path(os.getenv("WEB_TEMPLATE_PATH", base_dir / "config.json")),
        workdir=Path(os.getenv("WEB_WORKDIR", base_dir)),
        admin_password=admin_password,
        session_secret=session_secret,
    )


def _save_sources_from_request(form, settings: AppSettings) -> None:
    raw = _mapping_from_sources_form(form, settings)
    save_mapping_raw(settings.mapping_path, raw)


def _mapping_from_sources_form(form, settings: AppSettings) -> dict:
    raw = load_mapping_raw(settings.mapping_path)
    source_ids = form.getlist("source_id")
    source_urls = form.getlist("source_url")
    source_enabled = form.getlist("source_enabled")
    source_formats = form.getlist("source_format")
    sources: list[dict] = []
    for idx, source_id in enumerate(source_ids):
        if not source_id.strip():
            continue
        sources.append(
            {
                "id": source_id.strip(),
                "url": source_urls[idx].strip(),
                "enabled": source_enabled[idx].strip().lower() == "true",
                "format": source_formats[idx].strip() or "clash",
            }
        )
    raw["sources"] = sources
    return raw


def _source_from_form_index(form, index: int) -> dict:
    source_ids = form.getlist("source_id")
    source_urls = form.getlist("source_url")
    source_enabled = form.getlist("source_enabled")
    source_formats = form.getlist("source_format")
    if not 0 <= index < len(source_ids):
        raise ValueError("未找到要检测的订阅源。")
    source_id = source_ids[index].strip()
    if not source_id:
        raise ValueError("请先填写订阅源 ID，再执行立即检测。")
    return {
        "id": source_id,
        "url": source_urls[index].strip(),
        "enabled": source_enabled[index].strip().lower() == "true",
        "format": source_formats[index].strip() or "clash",
    }


def _mapping_from_groups_form(form, settings: AppSettings) -> dict:
    raw = load_mapping_raw(settings.mapping_path)
    existing_groups = list(raw.get("groups", []))
    names = form.getlist("group_name")
    filters = form.getlist("group_filter")
    excludes = form.getlist("group_exclude")
    sources = form.getlist("group_sources")
    starts = form.getlist("group_start")
    ends = form.getlist("group_end")
    groups: list[dict] = []
    for idx, name in enumerate(names):
        stripped_name = name.strip()
        if not stripped_name:
            continue
        start_text = starts[idx].strip()
        end_text = ends[idx].strip()
        if not start_text or not end_text:
            raise ValueError(f"分组 {name.strip()} 缺少端口范围，请填写起始端口和结束端口。")
        preserved_group = next(
            (item for item in existing_groups if item.get("name") == stripped_name),
            None,
        )
        if preserved_group is None and idx < len(existing_groups):
            preserved_group = existing_groups[idx]
        group_payload = dict(preserved_group or {})
        group_payload.update({
            "name": stripped_name,
            "filter": filters[idx].strip(),
            "port_range": {
                "start": int(start_text),
                "end": int(end_text),
            },
        })
        if excludes[idx].strip():
            group_payload["exclude"] = excludes[idx].strip()
        else:
            group_payload.pop("exclude", None)
        source_ids = [item.strip() for item in sources[idx].split(",") if item.strip()]
        if source_ids:
            group_payload["source_ids"] = source_ids
        else:
            group_payload.pop("source_ids", None)
        groups.append(group_payload)
    raw["groups"] = groups
    return raw


def build_sources_context(
    request: Request,
    mapping: dict,
    *,
    saved: bool = False,
    check_result: dict | None = None,
    check_index: int | None = None,
    import_message: str | None = None,
    import_error: str | None = None,
    node_preview: list[dict] | None = None,
) -> dict:
    return {
        "request": request,
        "mapping": mapping,
        "saved": saved,
        "check_result": check_result,
        "check_index": check_index,
        "import_message": import_message,
        "import_error": import_error,
        "node_preview": node_preview,
    }


def build_dashboard_context(
    request: Request,
    mapping: dict,
    *,
    saved: bool = False,
    generate_error: str | None = None,
) -> dict:
    return {
        "request": request,
        "mapping": mapping,
        "report_summary": load_report_summary(
            resolve_runtime_path(request.app.state.settings.workdir, mapping, "report_path")
        ),
        "state_groups": load_state_groups(
            resolve_runtime_path(request.app.state.settings.workdir, mapping, "state_path")
        ),
        "saved": saved,
        "generate_error": generate_error,
    }


def build_groups_context(
    request: Request,
    mapping: dict,
    *,
    saved: bool = False,
    error: str | None = None,
    builder_group: dict | None = None,
    builder_regions: list[dict] | None = None,
    builder_nodes: list[dict] | None = None,
) -> dict:
    return {
        "request": request,
        "mapping": mapping,
        "saved": saved,
        "error": error,
        "builder_group": builder_group,
        "builder_regions": builder_regions or [],
        "builder_nodes": builder_nodes or [],
    }


def resolve_runtime_path(workdir: Path, mapping: dict, key: str) -> Path:
    runtime_path = Path(mapping.get("runtime", {}).get(key, ""))
    if runtime_path.is_absolute():
        return runtime_path
    return workdir / runtime_path


def build_artifact_paths(workdir: Path, mapping: dict) -> dict[str, str]:
    return {
        "config": str(resolve_runtime_path(workdir, mapping, "output_path")),
        "report": str(resolve_runtime_path(workdir, mapping, "report_path")),
        "state": str(resolve_runtime_path(workdir, mapping, "state_path")),
    }


def describe_issue_reason(reason: str) -> str:
    if reason in ISSUE_REASON_LABELS:
        return ISSUE_REASON_LABELS[reason]
    if reason.startswith("unsupported_protocol:"):
        protocol = reason.split(":", 1)[1]
        return f"暂不支持的协议：{protocol}"
    return reason
