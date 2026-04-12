import json
from pathlib import Path

from xui_port_pool_generator.grouping import group_nodes
from xui_port_pool_generator.mapping_loader import load_mapping
from xui_port_pool_generator.models import NormalizedNode
from xui_port_pool_generator.pipeline import build_nodes_snapshot


def load_snapshot(path: Path) -> dict:
    if not path.exists():
        return {"summary": {}, "items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_snapshot_path(mapping_path: Path, workdir: Path) -> Path:
    mapping = load_mapping(mapping_path)
    output_path = _resolve_runtime_path(workdir, mapping.runtime.output_path)
    return output_path.parent / "nodes.snapshot.json"


def upsert_source_snapshot(
    mapping_path: Path,
    workdir: Path,
    source_id: str,
    nodes: list[NormalizedNode],
) -> None:
    mapping = load_mapping(mapping_path)
    snapshot_path = _resolve_runtime_path(workdir, mapping.runtime.output_path).parent / "nodes.snapshot.json"
    snapshot = load_snapshot(snapshot_path)
    matched, _ = group_nodes(nodes, mapping.groups)
    incoming_items = build_nodes_snapshot(nodes, matched, [])["items"]
    preserved_items = [
        item for item in snapshot.get("items", [])
        if item.get("source_id") != source_id
    ]
    _write_snapshot(snapshot_path, [*preserved_items, *incoming_items])


def build_region_index(snapshot: dict) -> list[dict]:
    counts: dict[str, int] = {}
    for item in snapshot.get("items", []):
        for tag in item.get("region_tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    return [
        {"tag": tag, "count": counts[tag]}
        for tag in sorted(counts.keys())
    ]


def filter_snapshot_for_group(snapshot: dict, group_name: str) -> list[dict]:
    items = snapshot.get("items", [])
    return [
        item for item in items
        if item.get("matched_group") == group_name or item.get("matched_group") is None
    ]


def _write_snapshot(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {
            "node_count": len(items),
            "matched_count": sum(1 for item in items if item.get("matched_group")),
            "assigned_count": sum(1 for item in items if item.get("assigned_port") is not None),
        },
        "items": items,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _resolve_runtime_path(workdir: Path, configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return workdir / path
