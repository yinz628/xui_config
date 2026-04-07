import base64
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml
from fastapi import UploadFile

from xui_port_pool_generator.clash_parser import parse_clash_subscription_with_issues
from xui_port_pool_generator.models import SourceConfig
from xui_port_pool_generator.subscriptions import fetch_source_to_cache


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
) -> dict:
    if not upload_file.filename:
        raise ValueError("未选择文件")

    imports_dir = config_dir / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(upload_file.filename)
    target_path = imports_dir / safe_name
    content = upload_file.file.read()
    target_path.write_bytes(content)

    nodes, issues = parse_clash_subscription_with_issues("import", target_path)
    if not nodes:
        target_path.unlink(missing_ok=True)
        reason = issues[0]["reason"] if issues else "未识别到节点"
        raise ValueError(f"导入失败：{reason}")

    source_id = _next_import_source_id(existing_ids)
    return {
        "source": {
            "id": source_id,
            "url": path_to_file_url(target_path),
            "enabled": True,
            "format": "clash",
        },
        "node_count": len(nodes),
    }


def parse_node_payload(text: str) -> list[dict]:
    payload = text.strip()
    if not payload:
        return []

    decoded_payload = _maybe_decode_subscription_blob(payload)
    yaml_obj = yaml.safe_load(decoded_payload)
    if isinstance(yaml_obj, dict) and isinstance(yaml_obj.get("proxies"), list):
        return [
            _proxy_preview(proxy)
            for proxy in yaml_obj["proxies"]
            if isinstance(proxy, dict)
        ]

    previews: list[dict] = []
    for line in decoded_payload.splitlines():
        line = line.strip()
        if not line:
            continue
        preview = _parse_uri_line(line)
        if preview:
            previews.append(preview)
    return previews


def path_to_file_url(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if len(resolved) >= 2 and resolved[1] == ":":
        return f"file:///{resolved}"
    return f"file://{resolved}"


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", name)


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


def _parse_uri_line(line: str) -> dict | None:
    if line.startswith("vmess://"):
        try:
            encoded = line[len("vmess://") :]
            encoded += "=" * (-len(encoded) % 4)
            payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
            return {
                "name": payload.get("ps", "<vmess>"),
                "type": "vmess",
                "server": payload.get("add", "-"),
                "port": str(payload.get("port", "-")),
            }
        except Exception:  # noqa: BLE001
            return {"name": "<vmess>", "type": "vmess", "server": "-", "port": "-"}

    if line.startswith(("vless://", "trojan://", "ss://", "socks5://")):
        parsed = urlsplit(line)
        return {
            "name": unquote(parsed.fragment) or parsed.scheme,
            "type": parsed.scheme,
            "server": parsed.hostname or "-",
            "port": str(parsed.port or "-"),
        }

    return None


def _maybe_decode_subscription_blob(payload: str) -> str:
    compact = payload.strip()
    if "\n" in compact:
        return compact
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", compact):
        return compact
    try:
        padded = compact + "=" * (-len(compact) % 4)
        decoded = base64.b64decode(padded).decode("utf-8")
    except Exception:  # noqa: BLE001
        return compact
    if any(
        marker in decoded
        for marker in ("vmess://", "vless://", "trojan://", "ss://", "proxies:")
    ):
        return decoded
    return compact
