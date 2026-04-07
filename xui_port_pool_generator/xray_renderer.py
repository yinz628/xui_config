import copy

from .models import AssignedNode


SPECIAL_OUTBOUND_TAGS = {"direct", "blocked", "api", "warp"}
DEFAULT_HTTP_HEADER = {
    "type": "http",
    "request": {
        "version": "1.1",
        "method": "GET",
        "path": ["/"],
        "headers": {
            "Host": ["example.com"],
            "User-Agent": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ],
            "Accept-Encoding": ["gzip, deflate"],
            "Connection": ["keep-alive"],
            "Pragma": ["no-cache"],
        },
    },
}


def render_xray_config(
    template: dict,
    assigned_nodes: list[AssignedNode],
    inbound_listen: str | None = "0.0.0.0",
) -> tuple[dict, list[dict]]:
    api_inbound = next(
        (copy.deepcopy(item) for item in template.get("inbounds", []) if item.get("tag") == "api"),
        None,
    )
    inbound_template = next(
        (
            copy.deepcopy(item)
            for item in template.get("inbounds", [])
            if str(item.get("tag", "")).startswith("inbound-")
        ),
        None,
    )
    special_outbounds = [
        copy.deepcopy(item)
        for item in template.get("outbounds", [])
        if item.get("tag") in SPECIAL_OUTBOUND_TAGS
    ]

    result = copy.deepcopy(template)
    result["inbounds"] = [api_inbound] if api_inbound else []
    result["outbounds"] = special_outbounds
    result["routing"] = {"domainStrategy": "AsIs", "rules": []}
    issues: list[dict] = []

    for item in assigned_nodes:
        result["inbounds"].append(
            build_inbound(item.port, inbound_template, listen=inbound_listen)
        )
        outbound, mode = build_outbound(item.node.raw_proxy)
        result["outbounds"].append(outbound)
        result["routing"]["rules"].append(
            {
                "type": "field",
                "inboundTag": [f"inbound-{item.port}"],
                "outboundTag": outbound["tag"],
            }
        )
        if mode != "exact":
            issues.append(
                {
                    "group_name": item.group_name,
                    "node_name": item.node.display_name,
                    "reason": mode,
                    "port": item.port,
                }
            )

    result["routing"]["rules"].extend(
        [
            {"inboundTag": ["api"], "outboundTag": "api", "type": "field"},
            {"ip": ["geoip:private"], "outboundTag": "blocked", "type": "field"},
            {"outboundTag": "blocked", "protocol": ["bittorrent"], "type": "field"},
        ]
    )
    return result, issues


def build_inbound(port: int, template: dict | None, listen: str | None) -> dict:
    if template:
        inbound = copy.deepcopy(template)
    else:
        inbound = {
            "listen": "0.0.0.0",
            "protocol": "socks",
            "settings": {"auth": "noauth", "ip": "127.0.0.1", "udp": True},
            "sniffing": {
                "destOverride": ["http", "tls", "quic", "fakedns"],
                "enabled": True,
                "metadataOnly": False,
                "routeOnly": False,
            },
            "streamSettings": None,
        }
    if listen is None:
        inbound.pop("listen", None)
    else:
        inbound["listen"] = listen
    inbound["port"] = port
    inbound["tag"] = f"inbound-{port}"
    return inbound


def build_stream_settings(
    *,
    network: str = "tcp",
    tls_enabled: bool = False,
    allow_insecure: bool | None = None,
    server_name: str | None = None,
    host: str | None = None,
    path: str | None = None,
    fingerprint: str | None = None,
    alpn: list[str] | None = None,
    http_obfs_host: str | None = None,
) -> dict:
    settings = {
        "network": "ws" if network == "ws" else "tcp",
        "security": "tls" if tls_enabled else "none",
    }
    if settings["network"] == "tcp":
        header = {"type": "none"}
        if http_obfs_host:
            header = copy.deepcopy(DEFAULT_HTTP_HEADER)
            header["request"]["headers"]["Host"] = [http_obfs_host]
        settings["tcpSettings"] = {"header": header}
    if settings["network"] == "ws":
        settings["wsSettings"] = {
            "heartbeatPeriod": 0,
            "host": host or "",
            "path": path or "/",
        }
    if tls_enabled:
        tls_settings = {"allowInsecure": bool(allow_insecure)}
        if server_name:
            tls_settings["serverName"] = server_name
        if fingerprint:
            tls_settings["fingerprint"] = fingerprint
        if alpn:
            tls_settings["alpn"] = alpn
        settings["tlsSettings"] = tls_settings
    return settings


def decode_alpn(items: list[str] | None) -> list[str] | None:
    if not items:
        return None
    decoded: list[str] = []
    for item in items:
        normalized = str(item).replace("%2F", "/").replace("%2C", ",")
        decoded.extend(part for part in normalized.split(",") if part)
    return decoded or None


def build_outbound(proxy: dict) -> tuple[dict, str]:
    proxy_type = proxy["type"]
    tag = proxy["name"]
    if proxy_type == "ss":
        server = {
            "address": proxy["server"],
            "method": proxy["cipher"],
            "password": proxy["password"],
            "port": proxy["port"],
        }
        if proxy.get("udp"):
            server["uot"] = True
        outbound = {
            "protocol": "shadowsocks",
            "settings": {"servers": [server]},
            "streamSettings": build_stream_settings(),
            "tag": tag,
        }
        if proxy.get("plugin") == "obfs":
            host = ((proxy.get("plugin-opts") or {}).get("host") or proxy["server"])
            outbound["streamSettings"] = build_stream_settings(http_obfs_host=host)
            return outbound, "inferred_obfs"
        return outbound, "exact"
    if proxy_type == "vmess":
        ws_opts = proxy.get("ws-opts") or {}
        headers = ws_opts.get("headers") or {}
        outbound = {
            "protocol": "vmess",
            "settings": {
                "vnext": [
                    {
                        "address": proxy["server"],
                        "port": proxy["port"],
                        "users": [
                            {
                                "alterId": proxy.get("alterId", 0),
                                "id": proxy["uuid"],
                                "security": proxy.get("cipher", "auto"),
                            }
                        ],
                    }
                ]
            },
            "streamSettings": build_stream_settings(
                network=proxy.get("network") or "tcp",
                tls_enabled=bool(proxy.get("tls")),
                allow_insecure=proxy.get("skip-cert-verify"),
                server_name=proxy.get("servername") or proxy["server"],
                host=headers.get("Host") or headers.get("host"),
                path=ws_opts.get("path"),
            ),
            "tag": tag,
        }
        return outbound, "exact"
    if proxy_type == "vless":
        ws_opts = proxy.get("ws-opts") or {}
        headers = ws_opts.get("headers") or {}
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": proxy["server"],
                        "port": proxy["port"],
                        "users": [{"encryption": "none", "id": proxy["uuid"]}],
                    }
                ]
            },
            "streamSettings": build_stream_settings(
                network=proxy.get("network") or "tcp",
                tls_enabled=bool(proxy.get("tls")),
                allow_insecure=proxy.get("skip-cert-verify"),
                server_name=proxy.get("servername") or proxy["server"],
                host=headers.get("Host") or headers.get("host"),
                path=ws_opts.get("path"),
                fingerprint=proxy.get("client-fingerprint"),
                alpn=decode_alpn(proxy.get("alpn")),
            ),
            "tag": tag,
        }
        return outbound, "exact"
    if proxy_type == "trojan":
        outbound = {
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": proxy["server"],
                        "password": proxy["password"],
                        "port": proxy["port"],
                    }
                ]
            },
            "streamSettings": build_stream_settings(
                tls_enabled=True,
                allow_insecure=proxy.get("skip-cert-verify"),
                server_name=proxy.get("sni") or proxy["server"],
            ),
            "tag": tag,
        }
        return outbound, "exact"
    if proxy_type == "socks5":
        outbound = {
            "protocol": "socks",
            "settings": {
                "servers": [
                    {
                        "address": proxy["server"],
                        "port": proxy["port"],
                        "users": (
                            [{"user": proxy["username"], "pass": proxy["password"]}]
                            if proxy.get("username") or proxy.get("password")
                            else []
                        ),
                    }
                ]
            },
            "tag": tag,
        }
        return outbound, "exact"
    return {"protocol": "blackhole", "settings": {}, "tag": tag}, f"unsupported_protocol:{proxy_type}"
