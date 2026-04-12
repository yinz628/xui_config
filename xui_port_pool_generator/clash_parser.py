from pathlib import Path

from .models import NormalizedNode
from .subscription_payloads import extract_proxies_from_payload


def parse_clash_subscription(source_id: str, path: Path) -> list[NormalizedNode]:
    nodes, _ = parse_clash_subscription_with_issues(source_id, path)
    return nodes


def parse_clash_subscription_with_issues(
    source_id: str,
    path: Path,
) -> tuple[list[NormalizedNode], list[dict]]:
    nodes: list[NormalizedNode] = []
    issues: list[dict] = []

    proxies = extract_proxies_from_payload(path.read_text(encoding="utf-8"))
    if not proxies:
        return (
            [],
            [
                {
                    "group_name": None,
                    "node_name": "<subscription>",
                    "reason": "parse_error_invalid_subscription_payload",
                    "source_id": source_id,
                }
            ],
        )

    for proxy in proxies:
        missing_fields = [
            field for field in ("name", "type", "server", "port") if field not in proxy
        ]
        if missing_fields:
            issues.append(
                {
                    "group_name": None,
                    "node_name": proxy.get("name", "<unknown>"),
                    "reason": f"parse_error_missing_{missing_fields[0]}",
                    "source_id": source_id,
                }
            )
            continue
        try:
            server_port = int(proxy["port"])
        except (TypeError, ValueError):
            issues.append(
                {
                    "group_name": None,
                    "node_name": proxy.get("name", "<unknown>"),
                    "reason": "parse_error_invalid_port",
                    "source_id": source_id,
                }
            )
            continue
        nodes.append(
            NormalizedNode(
                source_id=source_id,
                source_path=path,
                display_name=proxy["name"],
                protocol=proxy["type"],
                server=proxy["server"],
                server_port=server_port,
                raw_proxy=proxy,
            )
        )
    return nodes, issues
