from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from xui_port_pool_generator_web.app import AppSettings, create_app


def create_workspace(tmp_path: Path) -> AppSettings:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    config_dir.mkdir()
    (data_dir / "state").mkdir(parents=True)
    output_dir.mkdir()

    (config_dir / "mapping.yaml").write_text(
        """
version: 1
sources:
  - id: airport_a
    url: https://example.com/a
    enabled: true
    format: clash
groups:
  - name: tg_hk
    filter: "(?i)hk"
    port_range:
      start: 20000
      end: 20009
runtime:
  cache_dir: ./cache/subscriptions
  state_path: ./data/state/port_bindings.json
  output_path: ./output/config.generated.json
  report_path: ./output/config.generated.report.json
  output_mode: config_json
""".strip(),
        encoding="utf-8",
    )
    (config_dir / "config.json").write_text(
        '{"inbounds":[],"outbounds":[],"routing":{"rules":[]}}',
        encoding="utf-8",
    )
    return AppSettings(
        base_dir=tmp_path,
        mapping_path=config_dir / "mapping.yaml",
        template_path=config_dir / "config.json",
        workdir=tmp_path,
        admin_password="secret-pass",
        session_secret="session-secret",
    )


def login(client: TestClient) -> None:
    client.post("/login", data={"password": "secret-pass"})


def test_sources_page_contains_check_import_and_node_tools(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.get("/sources")

    assert response.status_code == 200
    assert "立即检测" in response.text
    assert "删除" in response.text
    assert "导入 YAML 文件" in response.text
    assert "节点数据识别" in response.text
    assert "新增一行" in response.text


def test_sources_check_reports_subscription_status(tmp_path: Path, monkeypatch) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    monkeypatch.setattr(
        "xui_port_pool_generator_web.app.inspect_source_url",
        lambda url, source_format: {"ok": True, "message": "检测成功：12 个节点"},
    )

    response = client.post(
        "/sources/check",
        data={
            "source_id": ["airport_a"],
            "source_url": ["https://example.com/a"],
            "source_enabled": ["true"],
            "source_format": ["clash"],
            "check_index": "0",
        },
    )

    assert response.status_code == 200
    assert "检测成功：12 个节点" in response.text


def test_import_yaml_upload_adds_local_file_source(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/sources/import-yaml",
        files={
            "yaml_file": (
                "manual.yaml",
                b"proxies:\n  - name: HK 01\n    type: ss\n    server: hk.example.com\n    port: 443\n    cipher: aes-128-gcm\n    password: pw\n",
                "application/x-yaml",
            )
        },
    )

    saved = yaml.safe_load(settings.mapping_path.read_text(encoding="utf-8"))
    imports_dir = settings.mapping_path.parent / "imports"

    assert response.status_code == 200
    assert any(item["url"].startswith("file:///") for item in saved["sources"])
    assert imports_dir.exists()


def test_node_payload_inspector_parses_yaml_nodes(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/sources/inspect-nodes",
        data={
            "node_payload": """
proxies:
  - name: HK 01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
""".strip()
        },
    )

    assert response.status_code == 200
    assert "HK 01" in response.text
    assert "hk.example.com" in response.text
    assert "443" in response.text
