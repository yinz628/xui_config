import json
from pathlib import Path

from xui_port_pool_generator.clash_parser import parse_clash_subscription_with_issues
from xui_port_pool_generator.grouping import group_nodes
from xui_port_pool_generator.mapping_loader import load_mapping
from xui_port_pool_generator.pipeline import build_nodes_snapshot
from xui_port_pool_generator.subscriptions import fetch_source_to_cache


def refresh_snapshot_and_invalidate_generated(
    mapping_path: Path,
    workdir: Path,
) -> dict:
    mapping = load_mapping(mapping_path)
    cache_dir = resolve_runtime_path(workdir, mapping.runtime.cache_dir)
    output_path = resolve_runtime_path(workdir, mapping.runtime.output_path)
    report_path = resolve_runtime_path(workdir, mapping.runtime.report_path)
    state_path = resolve_runtime_path(workdir, mapping.runtime.state_path)
    snapshot_path = output_path.parent / "nodes.snapshot.json"

    nodes = []
    for source in mapping.sources:
        if not source.enabled:
            continue
        try:
            cached_path = fetch_source_to_cache(source, cache_dir)
        except Exception:  # noqa: BLE001
            continue
        parsed_nodes, _ = parse_clash_subscription_with_issues(
            source.id,
            cached_path,
        )
        nodes.extend(parsed_nodes)

    matched, _ = group_nodes(nodes, mapping.groups)
    snapshot = build_nodes_snapshot(nodes, matched, [])
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    output_path.unlink(missing_ok=True)
    report_path.unlink(missing_ok=True)
    state_path.unlink(missing_ok=True)
    return snapshot


def resolve_runtime_path(workdir: Path, configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return workdir / path
