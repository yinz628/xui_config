from pathlib import Path

import yaml

from .models import NormalizedNode


def parse_clash_subscription(source_id: str, path: Path) -> list[NormalizedNode]:
    nodes, _ = parse_clash_subscription_with_issues(source_id, path)
    return nodes


def parse_clash_subscription_with_issues(
    source_id: str,
    path: Path,
) -> tuple[list[NormalizedNode], list[dict]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    nodes: list[NormalizedNode] = []
    issues: list[dict] = []
    for proxy in raw.get("proxies", []):
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
