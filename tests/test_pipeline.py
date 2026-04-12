import base64
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


def test_run_pipeline_reports_non_mapping_subscription_payload(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "plain-sub.txt"
    source_path.write_text("dm1lc3M6Ly9leGFtcGxl\n", encoding="utf-8")
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

    assert result["summary"]["assigned_count"] == 0
    assert any(
        item["reason"] == "parse_error_invalid_subscription_payload"
        for item in report["issues"]
    )


def test_run_pipeline_accepts_base64_subscription_blob(tmp_path: Path) -> None:
    payload = "ss://YWVzLTEyOC1nY206cHc=@hk.example.com:443#HK%2001\n"
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    source_path = tmp_path / "base64-sub.txt"
    source_path.write_text(encoded, encoding="utf-8")
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
    config = json.loads((tmp_path / "config.generated.json").read_text(encoding="utf-8"))

    assert result["summary"]["assigned_count"] == 1
    assert any(item.get("tag") == "HK 01" for item in config.get("outbounds", []))


def test_run_pipeline_defaults_inbound_listen_to_all_interfaces(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.yaml"
    source_path.write_text(
        """
proxies:
  - name: HK 01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
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

    run_pipeline(mapping_path, Path(r"F:\x-ui\config.json"), tmp_path)
    config = json.loads((tmp_path / "config.generated.json").read_text(encoding="utf-8"))
    inbound = next(item for item in config["inbounds"] if item.get("tag") == "inbound-20000")

    assert inbound["listen"] == "0.0.0.0"


def test_run_pipeline_allows_custom_inbound_listen_value(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.yaml"
    source_path.write_text(
        """
proxies:
  - name: HK 01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
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
  inbound_listen: 192.168.2.195
""".strip(),
        encoding="utf-8",
    )

    run_pipeline(mapping_path, Path(r"F:\x-ui\config.json"), tmp_path)
    config = json.loads((tmp_path / "config.generated.json").read_text(encoding="utf-8"))
    inbound = next(item for item in config["inbounds"] if item.get("tag") == "inbound-20000")

    assert inbound["listen"] == "192.168.2.195"


def test_run_pipeline_writes_nodes_snapshot(tmp_path: Path) -> None:
    source_path = tmp_path / "source.yaml"
    source_path.write_text(
        """
proxies:
  - name: 香港 IEPL 01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
  - name: 美国家宽 01
    type: ss
    server: us.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
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
  - name: browser_us
    filter: "(?i)(us|usa)"
    port_range: {{start: 21000, end: 21009}}
runtime:
  cache_dir: ./cache/subscriptions
  state_path: ./state/port_bindings.json
  output_path: ./config.generated.json
  report_path: ./config.generated.report.json
  output_mode: config_json
""".strip(),
        encoding="utf-8",
    )

    run_pipeline(mapping_path, Path(r"F:\x-ui\config.json"), tmp_path)
    snapshot_path = tmp_path / "nodes.snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert snapshot["summary"]["node_count"] == 2
    assert snapshot["summary"]["matched_count"] == 2
    assert snapshot["items"][0]["node_uid"]
    assert snapshot["items"][0]["region_tags"]
    assert "hk" in snapshot["items"][0]["region_tags"]
