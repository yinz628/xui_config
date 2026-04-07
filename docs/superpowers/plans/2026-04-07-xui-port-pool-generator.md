# X-UI Port Pool Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a config-driven compiler that reads `mapping.yaml`, fetches multiple Clash subscriptions, groups nodes by rules, assigns stable per-group ports, and writes `config.generated.json`, `config.generated.report.json`, and `state/port_bindings.json`.

**Architecture:** Keep `F:\x-ui\generate_xray_config.py` as a thin CLI and move logic into `F:\x-ui\xui_port_pool_generator\`. The runtime flow is `mapping load -> source fetch -> Clash parse -> group match -> stable key build -> stateful port allocation -> Xray/report/state render`.

**Tech Stack:** Python 3, PyYAML, pathlib, hashlib, json, urllib.request, pytest

**Workspace note:** `F:\x-ui` is not currently a Git repository. Commit steps are included for when Git is enabled later; if the workspace remains non-Git, skip only those commit commands.

---

## File Map

- Modify: `F:\x-ui\generate_xray_config.py`
  Purpose: CLI only; parse `--mapping` and `--template`, call the pipeline, print summary JSON.
- Create: `F:\x-ui\mapping.yaml`
  Purpose: sole user-maintained config entrypoint.
- Create: `F:\x-ui\xui_port_pool_generator\__init__.py`
  Purpose: package marker.
- Create: `F:\x-ui\xui_port_pool_generator\models.py`
  Purpose: dataclasses for config, normalized nodes, and assignments.
- Create: `F:\x-ui\xui_port_pool_generator\mapping_loader.py`
  Purpose: load and validate `mapping.yaml`.
- Create: `F:\x-ui\xui_port_pool_generator\subscriptions.py`
  Purpose: cache source content by `source_id`; never trust original filenames.
- Create: `F:\x-ui\xui_port_pool_generator\clash_parser.py`
  Purpose: parse Clash `proxies` into `NormalizedNode`.
- Create: `F:\x-ui\xui_port_pool_generator\grouping.py`
  Purpose: apply `first match wins` and `exclude`.
- Create: `F:\x-ui\xui_port_pool_generator\stable_keys.py`
  Purpose: build `node_uid` and `name_affinity_key`.
- Create: `F:\x-ui\xui_port_pool_generator\state_store.py`
  Purpose: load and save `state/port_bindings.json`.
- Create: `F:\x-ui\xui_port_pool_generator\allocator.py`
  Purpose: reuse or assign ports inside each group without cross-group borrowing.
- Create: `F:\x-ui\xui_port_pool_generator\xray_renderer.py`
  Purpose: render assigned nodes into Xray config using the existing template.
- Create: `F:\x-ui\xui_port_pool_generator\reporting.py`
  Purpose: build the JSON report.
- Create: `F:\x-ui\xui_port_pool_generator\pipeline.py`
  Purpose: orchestrate the full run.
- Create: `F:\x-ui\tests\test_mapping_loader.py`
- Create: `F:\x-ui\tests\test_sources_and_grouping.py`
- Create: `F:\x-ui\tests\test_allocator.py`
- Create: `F:\x-ui\tests\test_pipeline.py`
- Create: `F:\x-ui\tests\fixtures\template_config.json`
- Create: `F:\x-ui\tests\fixtures\source_airport_a.yaml`
- Create: `F:\x-ui\tests\fixtures\source_airport_b.yaml`

## Task 1: Add Config Models and Mapping Loader

**Files:**
- Create: `F:\x-ui\xui_port_pool_generator\models.py`
- Create: `F:\x-ui\xui_port_pool_generator\mapping_loader.py`
- Create: `F:\x-ui\mapping.yaml`
- Test: `F:\x-ui\tests\test_mapping_loader.py`

- [ ] **Step 1: Write the failing loader tests**

```python
from pathlib import Path

import pytest

from xui_port_pool_generator.mapping_loader import load_mapping


def test_load_mapping_reads_sources_groups_and_runtime(tmp_path: Path) -> None:
    path = tmp_path / "mapping.yaml"
    path.write_text(
        """
version: 1
sources:
  - id: airport_a
    url: https://example.com/a
    format: clash
groups:
  - name: tg_hk
    filter: "(?i)hk"
    port_range:
      start: 20000
      end: 20009
runtime:
  cache_dir: ./cache/subscriptions
  state_path: ./state/port_bindings.json
  output_path: ./config.generated.json
  report_path: ./config.generated.report.json
  output_mode: config_json
""".strip(),
        encoding="utf-8",
    )

    mapping = load_mapping(path)

    assert mapping.version == 1
    assert mapping.sources[0].id == "airport_a"
    assert mapping.groups[0].port_range.start == 20000


def test_load_mapping_rejects_overlapping_ranges(tmp_path: Path) -> None:
    path = tmp_path / "mapping.yaml"
    path.write_text(
        """
version: 1
sources:
  - id: airport_a
    url: https://example.com/a
    format: clash
groups:
  - name: tg_hk
    filter: "(?i)hk"
    port_range: {start: 20000, end: 20009}
  - name: browser_us
    filter: "(?i)us"
    port_range: {start: 20009, end: 20019}
runtime:
  cache_dir: ./cache/subscriptions
  state_path: ./state/port_bindings.json
  output_path: ./config.generated.json
  report_path: ./config.generated.report.json
  output_mode: config_json
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="overlap"):
        load_mapping(path)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_mapping_loader.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the models, loader, and default repo-local `mapping.yaml`**

```python
# F:\x-ui\xui_port_pool_generator\models.py
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PortRange:
    start: int
    end: int


@dataclass(frozen=True)
class SourceConfig:
    id: str
    url: str
    format: str
    enabled: bool = True


@dataclass(frozen=True)
class GroupConfig:
    name: str
    filter: str
    port_range: PortRange
    exclude: str | None = None
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeConfig:
    cache_dir: str
    state_path: str
    output_path: str
    report_path: str
    output_mode: str


@dataclass(frozen=True)
class MappingConfig:
    version: int
    sources: tuple[SourceConfig, ...]
    groups: tuple[GroupConfig, ...]
    runtime: RuntimeConfig


@dataclass(frozen=True)
class NormalizedNode:
    source_id: str
    source_path: Path
    display_name: str
    protocol: str
    server: str
    server_port: int
    raw_proxy: dict


@dataclass(frozen=True)
class AssignedNode:
    group_name: str
    port: int
    node_uid: str
    name_affinity_key: str
    node: NormalizedNode
```

```python
# F:\x-ui\xui_port_pool_generator\mapping_loader.py
from pathlib import Path

import yaml

from .models import GroupConfig, MappingConfig, PortRange, RuntimeConfig, SourceConfig


def load_mapping(path: Path) -> MappingConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = tuple(
        GroupConfig(
            name=item["name"],
            filter=item["filter"],
            exclude=item.get("exclude"),
            source_ids=tuple(item.get("source_ids", ())),
            port_range=PortRange(**item["port_range"]),
        )
        for item in raw["groups"]
    )
    _validate_ranges(groups)
    return MappingConfig(
        version=raw["version"],
        sources=tuple(SourceConfig(**item, enabled=item.get("enabled", True)) for item in raw["sources"]),
        groups=groups,
        runtime=RuntimeConfig(**raw["runtime"]),
    )


def _validate_ranges(groups: tuple[GroupConfig, ...]) -> None:
    occupied: set[int] = set()
    for group in groups:
        for port in range(group.port_range.start, group.port_range.end + 1):
            if port in occupied:
                raise ValueError(f"port range overlap detected at {port}")
            occupied.add(port)
```

```yaml
# F:\x-ui\mapping.yaml
version: 1
sources:
  - id: airport_a
    url: file:///F:/x-ui/310config86-106.yaml
    enabled: true
    format: clash
  - id: airport_b
    url: file:///F:/x-ui/RH5SFz15rrci.yaml
    enabled: true
    format: clash
groups:
  - name: tg_hk
    filter: '(?i)(hk|hong kong|香港)'
    exclude: '(?i)(iepl|iplc)'
    port_range: {start: 20000, end: 20049}
  - name: browser_us
    filter: '(?i)(us|united states|美国)'
    port_range: {start: 21000, end: 21049}
runtime:
  cache_dir: ./cache/subscriptions
  state_path: ./state/port_bindings.json
  output_path: ./config.generated.json
  report_path: ./config.generated.report.json
  output_mode: config_json
```

- [ ] **Step 4: Run the loader tests again**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_mapping_loader.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit this task if Git is enabled**

```powershell
git add F:\x-ui\mapping.yaml F:\x-ui\tests\test_mapping_loader.py F:\x-ui\xui_port_pool_generator\models.py F:\x-ui\xui_port_pool_generator\mapping_loader.py
git commit -m "feat(generator): 新增 mapping 配置加载"
```

## Task 2: Add Source Fetching, Clash Parsing, Grouping, and Stable Keys

**Files:**
- Create: `F:\x-ui\xui_port_pool_generator\subscriptions.py`
- Create: `F:\x-ui\xui_port_pool_generator\clash_parser.py`
- Create: `F:\x-ui\xui_port_pool_generator\grouping.py`
- Create: `F:\x-ui\xui_port_pool_generator\stable_keys.py`
- Test: `F:\x-ui\tests\test_sources_and_grouping.py`

- [ ] **Step 1: Write the failing source/grouping tests**

```python
from pathlib import Path

from xui_port_pool_generator.clash_parser import parse_clash_subscription
from xui_port_pool_generator.grouping import group_nodes
from xui_port_pool_generator.models import GroupConfig, PortRange
from xui_port_pool_generator.stable_keys import build_name_affinity_key, build_node_uid


def test_random_filename_does_not_change_source_identity(tmp_path: Path) -> None:
    path = tmp_path / "RH5SFz15rrci.yaml"
    path.write_text("proxies:\n  - name: HK 01\n    type: ss\n    server: hk.example.com\n    port: 443\n    cipher: aes-128-gcm\n    password: pw\n", encoding="utf-8")
    node = parse_clash_subscription("airport_a", path)[0]

    assert node.source_id == "airport_a"
    assert build_name_affinity_key(node.display_name) == "hk 01"
    assert len(build_node_uid(node)) == 24


def test_group_nodes_uses_first_match_wins_and_exclude(tmp_path: Path) -> None:
    path = tmp_path / "source.yaml"
    path.write_text("proxies:\n  - name: HK IEPL 01\n    type: ss\n    server: hk.example.com\n    port: 443\n    cipher: aes-128-gcm\n    password: pw\n", encoding="utf-8")
    node = parse_clash_subscription("airport_a", path)[0]
    groups = (
        GroupConfig(name="tg_hk", filter="(?i)hk", exclude="(?i)iepl", port_range=PortRange(20000, 20009)),
        GroupConfig(name="fallback_hk", filter="(?i)hk", port_range=PortRange(20010, 20019)),
    )

    matched, dropped = group_nodes([node], groups)

    assert [name for name, _ in matched] == ["fallback_hk"]
    assert dropped == []
```

- [ ] **Step 2: Run the tests and confirm they fail**

```powershell
python -m pytest F:\x-ui\tests\test_sources_and_grouping.py -q
```

Expected: FAIL with missing modules.

- [ ] **Step 3: Implement caching, parsing, grouping, and key generation**

```python
# F:\x-ui\xui_port_pool_generator\subscriptions.py
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


def fetch_source_to_cache(source, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{source.id}.yaml"
    parsed = urlparse(source.url)
    if parsed.scheme == "file":
        source_path = Path(parsed.path.lstrip("/"))
        target.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        with urlopen(source.url) as response:
            target.write_bytes(response.read())
    return target
```

```python
# F:\x-ui\xui_port_pool_generator\clash_parser.py / grouping.py / stable_keys.py
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import yaml

from .models import NormalizedNode


def parse_clash_subscription(source_id: str, path: Path) -> list[NormalizedNode]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        NormalizedNode(
            source_id=source_id,
            source_path=path,
            display_name=proxy["name"],
            protocol=proxy["type"],
            server=proxy["server"],
            server_port=int(proxy["port"]),
            raw_proxy=proxy,
        )
        for proxy in raw.get("proxies", [])
    ]


def group_nodes(nodes, groups):
    matched = []
    dropped = []
    for node in nodes:
        selected = None
        for group in groups:
            if not re.search(group.filter, node.display_name):
                continue
            if group.exclude and re.search(group.exclude, node.display_name):
                continue
            selected = group.name
            break
        if selected is None:
            dropped.append({"node": node.display_name, "reason": "group_not_matched"})
        else:
            matched.append((selected, node))
    return matched, dropped


def build_name_affinity_key(display_name: str) -> str:
    text = unicodedata.normalize("NFKC", display_name).lower()
    text = re.sub(r"[\U0001F1E6-\U0001F1FF]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def build_node_uid(node: NormalizedNode) -> str:
    payload = {
        "source_id": node.source_id,
        "protocol": node.protocol,
        "server": node.server,
        "server_port": node.server_port,
        "auth": {
            "cipher": node.raw_proxy.get("cipher"),
            "password": node.raw_proxy.get("password"),
            "uuid": node.raw_proxy.get("uuid"),
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
```

- [ ] **Step 4: Run the source/grouping tests again**

```powershell
python -m pytest F:\x-ui\tests\test_sources_and_grouping.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit this task if Git is enabled**

```powershell
git add F:\x-ui\tests\test_sources_and_grouping.py F:\x-ui\xui_port_pool_generator\subscriptions.py F:\x-ui\xui_port_pool_generator\clash_parser.py F:\x-ui\xui_port_pool_generator\grouping.py F:\x-ui\xui_port_pool_generator\stable_keys.py
git commit -m "feat(generator): 新增订阅解析与分组稳定键"
```

## Task 3: Add Stateful Port Allocation

**Files:**
- Create: `F:\x-ui\xui_port_pool_generator\state_store.py`
- Create: `F:\x-ui\xui_port_pool_generator\allocator.py`
- Test: `F:\x-ui\tests\test_allocator.py`

- [ ] **Step 1: Write the failing allocation tests**

```python
from pathlib import Path

from xui_port_pool_generator.allocator import allocate_group_ports
from xui_port_pool_generator.models import GroupConfig, NormalizedNode, PortRange


def make_node(name: str, server: str) -> NormalizedNode:
    return NormalizedNode("airport_a", Path("cache/airport_a.yaml"), name, "ss", server, 443, {"name": name, "type": "ss", "server": server, "port": 443, "cipher": "aes-128-gcm", "password": "pw"})


def test_allocator_reuses_existing_node_uid_binding() -> None:
    matched = [("tg_hk", make_node("HK 01", "hk.example.com"))]
    groups = {"tg_hk": GroupConfig(name="tg_hk", filter="(?i)hk", port_range=PortRange(20000, 20001))}
    state = {"version": 1, "groups": {"tg_hk": {"20000": {"node_uid": "fixed-node", "name_affinity_key": "hk 01", "source_id": "airport_a", "status": "active"}}}}

    assigned, issues = allocate_group_ports(matched, groups, state, lambda node: "fixed-node", lambda _: "hk 01")

    assert assigned[0].port == 20000
    assert issues == []


def test_allocator_marks_group_capacity_exceeded() -> None:
    matched = [("tg_hk", make_node("HK 01", "a.example.com")), ("tg_hk", make_node("HK 02", "b.example.com"))]
    groups = {"tg_hk": GroupConfig(name="tg_hk", filter="(?i)hk", port_range=PortRange(20000, 20000))}

    assigned, issues = allocate_group_ports(matched, groups, {"version": 1, "groups": {}}, lambda node: node.server, lambda name: name.lower())

    assert [item.port for item in assigned] == [20000]
    assert issues[0]["reason"] == "group_capacity_exceeded"
```

- [ ] **Step 2: Run the tests and confirm they fail**

```powershell
python -m pytest F:\x-ui\tests\test_allocator.py -q
```

Expected: FAIL with missing allocator/state modules.

- [ ] **Step 3: Implement state load/save and group-local allocation**

```python
# F:\x-ui\xui_port_pool_generator\state_store.py
import json
from pathlib import Path


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "groups": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

```python
# F:\x-ui\xui_port_pool_generator\allocator.py
from .models import AssignedNode


def allocate_group_ports(matched, groups_by_name, state, node_uid_factory, affinity_factory):
    assigned = []
    issues = []
    for group_name, node in matched:
        group = groups_by_name[group_name]
        history = state.setdefault("groups", {}).setdefault(group_name, {})
        node_uid = node_uid_factory(node)
        affinity = affinity_factory(node.display_name)
        port = _find_existing_port(history, node_uid) or _find_affinity_port(history, affinity) or _find_smallest_free_port(group.port_range.start, group.port_range.end, history)
        if port is None:
            issues.append({"group_name": group_name, "node_name": node.display_name, "reason": "group_capacity_exceeded"})
            continue
        history[str(port)] = {"node_uid": node_uid, "name_affinity_key": affinity, "source_id": node.source_id, "status": "active"}
        assigned.append(AssignedNode(group_name, port, node_uid, affinity, node))
    return assigned, issues
```

- [ ] **Step 4: Run the allocation tests again**

```powershell
python -m pytest F:\x-ui\tests\test_allocator.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit this task if Git is enabled**

```powershell
git add F:\x-ui\tests\test_allocator.py F:\x-ui\xui_port_pool_generator\state_store.py F:\x-ui\xui_port_pool_generator\allocator.py
git commit -m "feat(generator): 新增稳定端口分配"
```

## Task 4: Add Renderer, Pipeline, CLI Wiring, and Final Verification

**Files:**
- Create: `F:\x-ui\xui_port_pool_generator\xray_renderer.py`
- Create: `F:\x-ui\xui_port_pool_generator\reporting.py`
- Create: `F:\x-ui\xui_port_pool_generator\pipeline.py`
- Modify: `F:\x-ui\generate_xray_config.py`
- Test: `F:\x-ui\tests\test_pipeline.py`

- [ ] **Step 1: Write the failing pipeline test**

```python
import json
from pathlib import Path

from xui_port_pool_generator.pipeline import run_pipeline


def test_run_pipeline_writes_config_report_and_state(tmp_path: Path) -> None:
    result = run_pipeline(Path(r"F:\x-ui\mapping.yaml"), Path(r"F:\x-ui\config.json"), tmp_path)

    config = json.loads((tmp_path / "config.generated.json").read_text(encoding="utf-8"))
    report = json.loads((tmp_path / "config.generated.report.json").read_text(encoding="utf-8"))
    state = json.loads((tmp_path / "state" / "port_bindings.json").read_text(encoding="utf-8"))

    assert result["summary"]["assigned_count"] >= 1
    assert "inbounds" in config
    assert "summary" in report
    assert "groups" in state
```

- [ ] **Step 2: Run the test and confirm it fails**

```powershell
python -m pytest F:\x-ui\tests\test_pipeline.py -q
```

Expected: FAIL with missing pipeline/renderer modules.

- [ ] **Step 3: Implement rendering, reporting, orchestration, and CLI**

```python
# F:\x-ui\xui_port_pool_generator\pipeline.py
import json
from pathlib import Path

from .allocator import allocate_group_ports
from .clash_parser import parse_clash_subscription
from .grouping import group_nodes
from .mapping_loader import load_mapping
from .reporting import build_report
from .stable_keys import build_name_affinity_key, build_node_uid
from .state_store import load_state, save_state
from .subscriptions import fetch_source_to_cache
from .xray_renderer import render_xray_config


def run_pipeline(mapping_path: Path, template_path: Path, workdir: Path) -> dict:
    mapping = load_mapping(mapping_path)
    template = json.loads(template_path.read_text(encoding="utf-8"))
    state_path = workdir / "state" / "port_bindings.json"
    state = load_state(state_path)
    nodes = []
    for source in mapping.sources:
        if not source.enabled:
            continue
        cached = fetch_source_to_cache(source, workdir / "cache" / "subscriptions")
        nodes.extend(parse_clash_subscription(source.id, cached))
    matched, dropped = group_nodes(nodes, mapping.groups)
    assigned, allocation_issues = allocate_group_ports(matched, {group.name: group for group in mapping.groups}, state, build_node_uid, build_name_affinity_key)
    config = render_xray_config(template, assigned)
    report = build_report(mapping, matched, assigned, [*dropped, *allocation_issues])
    (workdir / "config.generated.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (workdir / "config.generated.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save_state(state_path, state)
    return {"summary": report["summary"]}
```

```python
# F:\x-ui\generate_xray_config.py
import argparse
import json
from pathlib import Path

from xui_port_pool_generator.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Xray config from mapping.yaml and subscription sources.")
    parser.add_argument("--mapping", default="mapping.yaml")
    parser.add_argument("--template", default="config.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_pipeline(Path(args.mapping), Path(args.template), Path.cwd())
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 4: Run the full targeted test suite**

```powershell
python -m pytest F:\x-ui\tests\test_mapping_loader.py F:\x-ui\tests\test_sources_and_grouping.py F:\x-ui\tests\test_allocator.py F:\x-ui\tests\test_pipeline.py -q
```

Expected: PASS with all tests green.

- [ ] **Step 5: Run the CLI smoke test and verify outputs**

```powershell
python F:\x-ui\generate_xray_config.py --mapping F:\x-ui\mapping.yaml --template F:\x-ui\config.json
@'
import json
from pathlib import Path

report = json.loads(Path(r"F:\x-ui\config.generated.report.json").read_text(encoding="utf-8"))
state = json.loads(Path(r"F:\x-ui\state\port_bindings.json").read_text(encoding="utf-8"))

assert "summary" in report
assert "issues" in report
assert "groups" in state
print("report/state verification passed")
'@ | python -
git add F:\x-ui\generate_xray_config.py F:\x-ui\mapping.yaml F:\x-ui\tests\test_pipeline.py F:\x-ui\xui_port_pool_generator
git commit -m "feat(generator): 打通端口池配置生成"
```

Expected: JSON summary printed, the three output files exist, the Python check prints `report/state verification passed`, and the Git commands succeed only if Git has been initialized.

## Self-Review

- Spec coverage:
  `mapping.yaml` structure is implemented in Task 1.
  Random filename independence, grouping, and stable keys are implemented in Task 2.
  Stable port reuse and group capacity enforcement are implemented in Task 3.
  Output boundary and end-to-end generation are implemented in Task 4.
- Placeholder scan:
  This plan contains no unresolved placeholder markers.
- Type consistency:
  `MappingConfig`, `NormalizedNode`, and `AssignedNode` are introduced before later tasks depend on them.
  `run_pipeline()` is defined only once and consumed by the CLI after Task 4.

## Execution Notes

- Move the existing outbound conversion helpers from `F:\x-ui\generate_xray_config.py` into `F:\x-ui\xui_port_pool_generator\xray_renderer.py` instead of re-typing protocol conversion logic.
- If a source contains unsupported protocols beyond `ss`, `vmess`, `vless`, and `trojan`, write a report issue and keep the generated config loadable.
- Do not add direct `x-ui.db` writes in this plan; that is outside the approved boundary.
