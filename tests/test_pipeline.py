import json
from pathlib import Path

from xui_port_pool_generator.pipeline import run_pipeline


def test_run_pipeline_writes_config_report_and_state(tmp_path: Path) -> None:
    result = run_pipeline(
        Path(r"F:\x-ui\mapping.yaml"),
        Path(r"F:\x-ui\config.json"),
        tmp_path,
    )

    config = json.loads(
        (tmp_path / "config.generated.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (tmp_path / "config.generated.report.json").read_text(encoding="utf-8")
    )
    state = json.loads(
        (tmp_path / "state" / "port_bindings.json").read_text(encoding="utf-8")
    )

    assert result["summary"]["assigned_count"] >= 1
    assert "inbounds" in config
    assert "summary" in report
    assert "groups" in state


def test_run_pipeline_reports_parse_errors_without_crashing(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "RH5SFz15rrci.yaml"
    source_path.write_text(
        """
proxies:
  - name: HK Good 01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
  - name: Broken Node
    type: anytls
    server: broken.example.com
""".strip(),
        encoding="utf-8",
    )
    mapping_path = tmp_path / "mapping.yaml"
    mapping_path.write_text(
        f"""
version: 1
sources:
  - id: airport_a
    url: file:///{source_path.as_posix()}
    format: clash
groups:
  - name: tg_hk
    filter: "(?i)hk"
    port_range: {{start: 20000, end: 20009}}
runtime:
  cache_dir: ./cache/subscriptions
  state_path: ./state/port_bindings.json
  output_path: ./config.generated.json
  report_path: ./config.generated.report.json
  output_mode: config_json
""".strip(),
        encoding="utf-8",
    )

    result = run_pipeline(mapping_path, Path(r"F:\x-ui\config.json"), tmp_path)
    report = json.loads(
        (tmp_path / "config.generated.report.json").read_text(encoding="utf-8")
    )

    assert result["summary"]["assigned_count"] == 1
    assert any(item["reason"] == "parse_error_missing_port" for item in report["issues"])
