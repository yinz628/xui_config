import re
import tempfile
from pathlib import Path

import yaml
from fastapi import UploadFile

from xui_port_pool_generator.clash_parser import parse_clash_subscription_with_issues
from xui_port_pool_generator.models import SourceConfig
from xui_port_pool_generator.subscriptions import fetch_source_to_cache

from .node_payloads import extract_proxies_from_payload


def inspect_source_url(url: str, source_format: str) -> dict:
    if source_format != "clash":
        return {"ok": False, "message": "暂不支持该格式的在线检测"}

    with tempfile.TemporaryDirectory() as tmpdir:
        source = SourceConfig(
            id="preview",
            url=url,
            format=source_format,
            enabled=True,
        )
        try:
            cached_path = fetch_source_to_cache(source, Path(tmpdir))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"检测失败：{exc}"}

        nodes, issues = parse_clash_subscription_with_issues("preview", cached_path)
        if not nodes:
            reason = issues[0]["reason"] if issues else "未识别到节点"
            return {"ok": False, "message": f"检测失败：{reason}"}

        return {"ok": True, "message": f"检测成功：{len(nodes)} 个节点"}


def import_yaml_source(
    upload_file: UploadFile,
    config_dir: Path,
    existing_ids: set[str],
    source_name: str = "",
) -> dict:
    if not upload_file.filename:
        raise ValueError("未选择文件")

    source_id = _resolve_source_id(source_name, existing_ids)
    target_path = _import_path(config_dir, source_id)
    target_path.write_bytes(upload_file.file.read())
    return _build_import_result(source_id, target_path)


def import_node_payload_source(
    text: str,
    config_dir: Path,
    existing_ids: set[str],
    source_name: str = "",
) -> dict:
    proxies = extract_proxies_from_payload(text)
    if not proxies:
        raise ValueError("未识别到节点")

    source_id = _resolve_source_id(source_name, existing_ids)
    target_path = _import_path(config_dir, source_id)
    target_path.write_text(
        yaml.safe_dump(
            {"proxies": proxies},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return _build_import_result(source_id, target_path)


def parse_node_payload(text: str) -> list[dict]:
    return [_proxy_preview(proxy) for proxy in extract_proxies_from_payload(text)]


def path_to_file_url(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if len(resolved) >= 2 and resolved[1] == ":":
        return f"file:///{resolved}"
    return f"file://{resolved}"


def _build_import_result(source_id: str, target_path: Path) -> dict:
    nodes, issues = parse_clash_subscription_with_issues(source_id, target_path)
    if not nodes:
        target_path.unlink(missing_ok=True)
        reason = issues[0]["reason"] if issues else "未识别到节点"
        raise ValueError(f"导入失败：{reason}")

    return {
        "source": {
            "id": source_id,
            "url": path_to_file_url(target_path),
            "enabled": True,
            "format": "clash",
        },
        "node_count": len(nodes),
        "node_preview": [_proxy_preview(node.raw_proxy) for node in nodes],
        "nodes": nodes,
    }


def _import_path(config_dir: Path, source_id: str) -> Path:
    imports_dir = config_dir / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    return imports_dir / f"{_sanitize_filename(source_id)}.yaml"


def _resolve_source_id(source_name: str, existing_ids: set[str]) -> str:
    normalized = _sanitize_source_name(source_name)
    if normalized:
        if normalized in existing_ids:
            raise ValueError(f"来源名称已存在：{normalized}")
        return normalized
    return _next_import_source_id(existing_ids)


def _sanitize_source_name(name: str) -> str:
    normalized = re.sub(r"\s+", "_", name.strip())
    normalized = re.sub(r"[^\w.-]", "_", normalized, flags=re.UNICODE)
    normalized = normalized.strip("._-")
    return normalized


def _sanitize_filename(name: str) -> str:
    sanitized = _sanitize_source_name(name)
    return sanitized or "imported_source"


def _next_import_source_id(existing_ids: set[str]) -> str:
    index = 1
    while True:
        candidate = f"import_{index}"
        if candidate not in existing_ids:
            return candidate
        index += 1


def _proxy_preview(proxy: dict) -> dict:
    return {
        "name": proxy.get("name", "<unknown>"),
        "type": proxy.get("type", "<unknown>"),
        "server": proxy.get("server", "-"),
        "port": str(proxy.get("port", "-")),
    }
