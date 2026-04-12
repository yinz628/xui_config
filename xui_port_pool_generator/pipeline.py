import json
from pathlib import Path

from .allocator import allocate_group_ports
from .clash_parser import parse_clash_subscription_with_issues
from .grouping import derive_region_tags, group_nodes
from .mapping_loader import load_mapping
from .reporting import build_report
from .stable_keys import build_name_affinity_key, build_node_uid
from .state_store import load_state, save_state
from .subscriptions import fetch_source_to_cache
from .xray_renderer import render_xray_config


def run_pipeline(mapping_path: Path, template_path: Path, workdir: Path) -> dict:
    mapping = load_mapping(mapping_path)
    template = json.loads(template_path.read_text(encoding="utf-8"))

    cache_dir = _resolve_runtime_path(workdir, mapping.runtime.cache_dir)
    output_path = _resolve_runtime_path(workdir, mapping.runtime.output_path)
    report_path = _resolve_runtime_path(workdir, mapping.runtime.report_path)
    state_path = _resolve_runtime_path(workdir, mapping.runtime.state_path)
    snapshot_path = output_path.parent / "nodes.snapshot.json"

    state = load_state(state_path)
    nodes = []
    parse_issues: list[dict] = []
    for source in mapping.sources:
        if not source.enabled:
            continue
        cached_path = fetch_source_to_cache(source, cache_dir)
        parsed_nodes, source_issues = parse_clash_subscription_with_issues(
            source.id,
            cached_path,
        )
        nodes.extend(parsed_nodes)
        parse_issues.extend(source_issues)

    matched, dropped = group_nodes(nodes, mapping.groups)
    assigned, allocation_issues = allocate_group_ports(
        matched,
        {group.name: group for group in mapping.groups},
        state,
        build_node_uid,
        build_name_affinity_key,
    )
    config, render_issues = render_xray_config(
        template,
        assigned,
        inbound_listen=mapping.runtime.inbound_listen,
    )
    report = build_report(
        mapping,
        matched,
        assigned,
        [*parse_issues, *dropped, *allocation_issues, *render_issues],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    snapshot_path.write_text(
        json.dumps(
            build_nodes_snapshot(nodes, matched, assigned),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    save_state(state_path, state)
    return {"summary": report["summary"]}


def _resolve_runtime_path(workdir: Path, configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return workdir / path


def build_nodes_snapshot(nodes, matched, assigned) -> dict:
    matched_by_uid = {build_node_uid(node): group_name for group_name, node in matched}
    assigned_by_uid = {item.node_uid: item.port for item in assigned}
    items = []
    for node in nodes:
        node_uid = build_node_uid(node)
        items.append(
            {
                "node_uid": node_uid,
                "display_name": node.display_name,
                "source_id": node.source_id,
                "protocol": node.protocol,
                "server": node.server,
                "server_port": node.server_port,
                "region_tags": derive_region_tags(node.display_name),
                "matched_group": matched_by_uid.get(node_uid),
                "assigned_port": assigned_by_uid.get(node_uid),
            }
        )
    return {
        "summary": {
            "node_count": len(nodes),
            "matched_count": len(matched),
            "assigned_count": len(assigned),
        },
        "items": items,
    }
