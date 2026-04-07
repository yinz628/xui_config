import json
from pathlib import Path
import tempfile

import yaml

from xui_port_pool_generator.mapping_loader import load_mapping


def load_mapping_raw(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_report_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    return report.get("summary", {})


def load_report(path: Path) -> dict:
    if not path.exists():
        return {"summary": {}, "issues": []}
    return json.loads(path.read_text(encoding="utf-8"))


def load_state_groups(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    state = json.loads(path.read_text(encoding="utf-8"))
    return {group: len(bindings) for group, bindings in state.get("groups", {}).items()}


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"groups": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_mapping_raw(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
    )
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yaml",
        delete=False,
    ) as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    try:
        load_mapping(temp_path)
        path.write_text(serialized, encoding="utf-8")
    finally:
        temp_path.unlink(missing_ok=True)
