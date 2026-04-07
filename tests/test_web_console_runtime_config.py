import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(r"F:\x-ui")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    (config_dir / "mapping.vps.example.yaml").write_text(
        "version: 1\nsources: []\ngroups: []\nruntime: {}\n",
        encoding="utf-8",
    )
    (config_dir / "config.json.example").write_text(
        '{"inbounds":[],"outbounds":[]}',
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


def test_runtime_config_page_shows_current_mapping_and_template_metadata(
    tmp_path: Path,
) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.get("/runtime-config")

    assert response.status_code == 200
    assert "mapping.yaml" in response.text
    assert "config.json" in response.text
    assert "mapping.vps.example.yaml" in response.text
    assert "config.json.example" in response.text


def test_runtime_config_page_exposes_upload_forms(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.get("/runtime-config")

    assert response.status_code == 200
    assert 'action="/runtime-config/upload-mapping"' in response.text
    assert 'action="/runtime-config/upload-template"' in response.text


def test_runtime_config_save_validates_mapping_yaml(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/runtime-config/save-mapping",
        data={
            "mapping_text": """
version: 1
sources:
  - id: airport_a
    url: https://example.com/a
    format: clash
groups:
  - name: tg_hk
    filter: "(?i)hk"
    port_range: {start: 20000, end: 20009}
runtime:
  cache_dir: ./cache/subscriptions
  state_path: ./data/state/port_bindings.json
  output_path: ./output/config.generated.json
  report_path: ./output/config.generated.report.json
  output_mode: config_json
""".strip()
        },
    )

    assert response.status_code == 200
    assert "运行态 mapping.yaml 已保存" in response.text


def test_runtime_config_save_rejects_invalid_template_json(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/runtime-config/save-template",
        data={"template_text": '{"inbounds":[]}'},
    )

    assert response.status_code == 400
    assert "outbounds" in response.text


def test_runtime_config_upload_mapping_replaces_runtime_file(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/runtime-config/upload-mapping",
        files={
            "mapping_file": (
                "mapping.yaml",
                b"version: 1\nsources: []\ngroups: []\nruntime:\n  cache_dir: ./cache\n  state_path: ./state.json\n  output_path: ./out.json\n  report_path: ./report.json\n  output_mode: config_json\n",
                "application/x-yaml",
            )
        },
    )

    assert response.status_code == 200
    assert "运行态 mapping.yaml 已上传" in response.text


def test_runtime_config_upload_template_rejects_invalid_json(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/runtime-config/upload-template",
        files={
            "template_file": (
                "config.json",
                b'{"inbounds":[]}',
                "application/json",
            )
        },
    )

    assert response.status_code == 400
    assert "outbounds" in response.text
