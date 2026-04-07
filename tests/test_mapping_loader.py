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
