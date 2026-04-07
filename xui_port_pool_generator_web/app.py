import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from xui_port_pool_generator.pipeline import run_pipeline

from .mapping_store import (
    load_mapping_raw,
    load_report,
    load_report_summary,
    load_state,
    load_state_groups,
    save_mapping_raw,
)
from .source_tools import (
    import_yaml_source,
    inspect_source_url,
    parse_node_payload,
)


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
        report_summary = load_report_summary(resolve_runtime_path(settings.workdir, mapping, "report_path"))
        state_groups = load_state_groups(resolve_runtime_path(settings.workdir, mapping, "state_path"))
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "request": request,
                "mapping": mapping,
                "report_summary": report_summary,
                "state_groups": state_groups,
                "saved": request.query_params.get("saved") == "1",
            },
        )

    @app.post("/dashboard/sources/save")
    async def dashboard_sources_save(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        _save_sources_from_request(await request.form(), settings)
        return RedirectResponse(url="/dashboard?saved=1", status_code=303)

    @app.post("/dashboard/sources/save-and-generate")
    async def dashboard_sources_save_and_generate(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        _save_sources_from_request(await request.form(), settings)
        run_pipeline(settings.mapping_path, settings.template_path, settings.workdir)
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
            {
                "request": request,
                "mapping": mapping,
                "saved": request.query_params.get("saved") == "1",
                "check_result": None,
                "check_index": None,
                "import_message": None,
                "node_preview": None,
            },
        )

    @app.post("/sources/save", response_class=HTMLResponse)
    async def sources_save(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        _save_sources_from_request(await request.form(), settings)
        return RedirectResponse(url="/sources?saved=1", status_code=303)

    @app.post("/sources/check", response_class=HTMLResponse)
    async def sources_check(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        form = await request.form()
        mapping = _mapping_from_sources_form(form, settings)
        index = int(form.get("check_index", 0))
        source = mapping["sources"][index]
        check_result = inspect_source_url(source["url"], source["format"])
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "request": request,
                "mapping": mapping,
                "saved": False,
                "check_result": check_result,
                "check_index": index,
                "import_message": None,
                "node_preview": None,
            },
        )

    @app.post("/sources/import-yaml", response_class=HTMLResponse)
    async def sources_import_yaml(request: Request, yaml_file: UploadFile = File(...)):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        raw = load_mapping_raw(settings.mapping_path)
        imported = import_yaml_source(
            yaml_file,
            settings.mapping_path.parent,
            {item["id"] for item in raw.get("sources", [])},
        )
        raw.setdefault("sources", []).append(imported["source"])
        save_mapping_raw(settings.mapping_path, raw)
        mapping = load_mapping_raw(settings.mapping_path)
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "request": request,
                "mapping": mapping,
                "saved": False,
                "check_result": None,
                "check_index": None,
                "import_message": f"导入成功：新增 {imported['source']['id']}，识别到 {imported['node_count']} 个节点。",
                "node_preview": None,
            },
        )

    @app.post("/sources/inspect-nodes", response_class=HTMLResponse)
    async def sources_inspect_nodes(request: Request, node_payload: str = Form(...)):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        mapping = load_mapping_raw(settings.mapping_path)
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "request": request,
                "mapping": mapping,
                "saved": False,
                "check_result": None,
                "check_index": None,
                "import_message": None,
                "node_preview": parse_node_payload(node_payload),
            },
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
            {
                "request": request,
                "mapping": mapping,
                "saved": request.query_params.get("saved") == "1",
                "error": None,
            },
        )

    @app.post("/groups/save", response_class=HTMLResponse)
    async def groups_save(request: Request):
        auth_redirect = ensure_authenticated(request)
        if auth_redirect:
            return auth_redirect
        form = await request.form()
        raw = load_mapping_raw(settings.mapping_path)
        names = form.getlist("group_name")
        filters = form.getlist("group_filter")
        excludes = form.getlist("group_exclude")
        sources = form.getlist("group_sources")
        starts = form.getlist("group_start")
        ends = form.getlist("group_end")
        groups: list[dict] = []
        for idx, name in enumerate(names):
            if not name.strip():
                continue
            group_payload = {
                "name": name.strip(),
                "filter": filters[idx].strip(),
                "port_range": {
                    "start": int(starts[idx]),
                    "end": int(ends[idx]),
                },
            }
            if excludes[idx].strip():
                group_payload["exclude"] = excludes[idx].strip()
            source_ids = [item.strip() for item in sources[idx].split(",") if item.strip()]
            if source_ids:
                group_payload["source_ids"] = source_ids
            groups.append(group_payload)
        raw["groups"] = groups
        try:
            save_mapping_raw(settings.mapping_path, raw)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "groups.html",
                {
                    "request": request,
                    "mapping": raw,
                    "saved": False,
                    "error": str(exc),
                },
                status_code=400,
            )
        return RedirectResponse(url="/groups?saved=1", status_code=303)

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
            },
        )

    return app


def ensure_authenticated(request: Request) -> RedirectResponse | None:
    if request.session.get("authenticated"):
        return None
    return RedirectResponse(url="/login", status_code=302)


def load_settings_from_env() -> AppSettings:
    base_dir = Path(os.getenv("WEB_BASE_DIR", Path(__file__).resolve().parents[1]))
    return AppSettings(
        base_dir=base_dir,
        mapping_path=Path(os.getenv("WEB_MAPPING_PATH", base_dir / "mapping.yaml")),
        template_path=Path(os.getenv("WEB_TEMPLATE_PATH", base_dir / "config.json")),
        workdir=Path(os.getenv("WEB_WORKDIR", base_dir)),
        admin_password=os.getenv("WEB_ADMIN_PASSWORD", "admin"),
        session_secret=os.getenv("WEB_SESSION_SECRET", "change-me"),
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


def resolve_runtime_path(workdir: Path, mapping: dict, key: str) -> Path:
    runtime_path = Path(mapping.get("runtime", {}).get(key, ""))
    if runtime_path.is_absolute():
        return runtime_path
    return workdir / runtime_path


app = create_app()
