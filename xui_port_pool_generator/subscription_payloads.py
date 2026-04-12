import base64
import json
import re
from urllib.parse import parse_qs, unquote, urlsplit

import yaml


def extract_proxies_from_payload(text: str) -> list[dict]:
    payload = text.strip()
    if not payload:
        return []

    decoded_payload = maybe_decode_subscription_blob(payload)
    yaml_obj = safe_load_yaml(decoded_payload)
    if isinstance(yaml_obj, dict) and isinstance(yaml_obj.get("proxies"), list):
        return [proxy for proxy in yaml_obj["proxies"] if isinstance(proxy, dict)]

    proxies: list[dict] = []
    for line in decoded_payload.splitlines():
        line = line.strip()
        if not line:
            continue
        proxy = parse_uri_proxy(line)
        if proxy:
            proxies.append(proxy)
    return proxies


def safe_load_yaml(text: str):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def parse_uri_proxy(line: str) -> dict | None:
    if line.startswith("vmess://"):
        return parse_vmess_proxy(line)
    if line.startswith("vless://"):
        return parse_vless_proxy(line)
    if line.startswith("trojan://"):
        return parse_trojan_proxy(line)
    if line.startswith("ss://"):
        return parse_ss_proxy(line)
    if line.startswith("socks5://"):
        return parse_socks5_proxy(line)
    return None


def parse_vmess_proxy(line: str) -> dict | None:
    encoded = line[len("vmess://") :]
    decoded = decode_base64_text(encoded)
    if not decoded:
        return None

    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError:
        return None

    server = payload.get("add")
    port = parse_port(payload.get("port"))
    uuid = payload.get("id")
    if not server or port is None or not uuid:
        return None

    network = payload.get("net") or "tcp"
    proxy = {
        "name": payload.get("ps") or server,
        "type": "vmess",
        "server": server,
        "port": port,
        "uuid": uuid,
        "alterId": parse_int(payload.get("aid"), 0),
        "cipher": payload.get("scy") or "auto",
        "network": network,
    }
    if is_truthy(payload.get("tls")):
        proxy["tls"] = True
    if payload.get("sni"):
        proxy["servername"] = payload["sni"]
    if network == "ws":
        ws_opts = {"path": payload.get("path") or "/"}
        if payload.get("host"):
            ws_opts["headers"] = {"Host": payload["host"]}
        proxy["ws-opts"] = ws_opts
    return proxy


def parse_vless_proxy(line: str) -> dict | None:
    parsed = urlsplit(line)
    server = parsed.hostname
    port = parsed.port
    uuid = unquote(parsed.username or "")
    if not server or port is None or not uuid:
        return None

    query = parse_qs(parsed.query)
    network = query_value(query, "type") or "tcp"
    proxy = {
        "name": unquote(parsed.fragment) or server,
        "type": "vless",
        "server": server,
        "port": port,
        "uuid": uuid,
        "network": network,
    }
    if (query_value(query, "security") or "").lower() == "tls":
        proxy["tls"] = True
    if query_value(query, "sni"):
        proxy["servername"] = query_value(query, "sni")
    if is_truthy(query_value(query, "allowInsecure")):
        proxy["skip-cert-verify"] = True
    if query_value(query, "fp"):
        proxy["client-fingerprint"] = query_value(query, "fp")
    if query_value(query, "alpn"):
        proxy["alpn"] = [query_value(query, "alpn")]
    if network == "ws":
        ws_opts = {"path": query_value(query, "path") or "/"}
        if query_value(query, "host"):
            ws_opts["headers"] = {"Host": query_value(query, "host")}
        proxy["ws-opts"] = ws_opts
    return proxy


def parse_trojan_proxy(line: str) -> dict | None:
    parsed = urlsplit(line)
    server = parsed.hostname
    port = parsed.port
    password = unquote(parsed.username or "")
    if not server or port is None or not password:
        return None

    query = parse_qs(parsed.query)
    proxy = {
        "name": unquote(parsed.fragment) or server,
        "type": "trojan",
        "server": server,
        "port": port,
        "password": password,
    }
    if query_value(query, "sni"):
        proxy["sni"] = query_value(query, "sni")
    if is_truthy(query_value(query, "allowInsecure")):
        proxy["skip-cert-verify"] = True
    return proxy


def parse_ss_proxy(line: str) -> dict | None:
    payload = line[len("ss://") :]
    link, _, fragment = payload.partition("#")
    core, _, query_text = link.partition("?")
    plugin = query_value(parse_qs(query_text), "plugin")

    decoded_core = decode_base64_text(core)
    if decoded_core and "@" in decoded_core:
        credentials, server_part = decoded_core.rsplit("@", 1)
    else:
        if "@" not in core:
            return None
        encoded_credentials, server_part = core.rsplit("@", 1)
        credentials = decode_base64_text(encoded_credentials) or encoded_credentials

    if ":" not in credentials:
        return None

    cipher, password = credentials.split(":", 1)
    server, port = split_host_port(server_part)
    if not server or port is None:
        return None

    proxy = {
        "name": unquote(fragment) or server,
        "type": "ss",
        "server": server,
        "port": port,
        "cipher": cipher,
        "password": password,
    }
    plugin_opts = parse_ss_plugin(plugin)
    if plugin_opts:
        proxy["plugin"] = "obfs"
        proxy["plugin-opts"] = plugin_opts
    return proxy


def parse_socks5_proxy(line: str) -> dict | None:
    parsed = urlsplit(line)
    server = parsed.hostname
    port = parsed.port
    if not server or port is None:
        return None

    proxy = {
        "name": unquote(parsed.fragment) or server,
        "type": "socks5",
        "server": server,
        "port": port,
    }
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    return proxy


def parse_ss_plugin(plugin: str | None) -> dict | None:
    if not plugin:
        return None

    items = [part for part in unquote(plugin).split(";") if part]
    if not items or not items[0].startswith("obfs"):
        return None

    options: dict[str, str] = {}
    for item in items[1:]:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key == "obfs-host":
            options["host"] = value
    return options or None


def split_host_port(raw: str) -> tuple[str | None, int | None]:
    host_port = raw.strip()
    if host_port.startswith("[") and "]:" in host_port:
        host, port_text = host_port[1:].split("]:", 1)
        return host, parse_port(port_text)
    if ":" not in host_port:
        return host_port, None
    host, port_text = host_port.rsplit(":", 1)
    return host, parse_port(port_text)


def decode_base64_text(value: str) -> str | None:
    compact = value.strip()
    padded = compact + "=" * (-len(compact) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(padded).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
    return None


def query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return unquote(values[0])


def parse_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_port(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "tls", "yes"}


def maybe_decode_subscription_blob(payload: str) -> str:
    compact = payload.strip()
    if not compact:
        return compact

    compact_no_ws = re.sub(r"\s+", "", compact)
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact_no_ws):
        return compact

    decoded = decode_base64_text(compact_no_ws)
    if not decoded:
        return compact

    if any(
        marker in decoded
        for marker in ("vmess://", "vless://", "trojan://", "ss://", "socks5://", "proxies:")
    ):
        return decoded
    return compact

