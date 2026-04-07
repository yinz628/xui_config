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
    exclude: "(?i)iepl"
    source_ids: []
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
    response = client.post("/login", data={"password": "secret-pass"})
    assert response.status_code == 200 or response.status_code in {302, 303}


def test_sources_save_updates_mapping_file(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/sources/save",
        data={
            "source_id": ["airport_a", "airport_b"],
            "source_url": ["https://example.com/a-updated", "https://example.com/b"],
            "source_enabled": ["true", "false"],
            "source_format": ["clash", "clash"],
        },
        follow_redirects=False,
    )

    saved = yaml.safe_load(settings.mapping_path.read_text(encoding="utf-8"))

    assert response.status_code in {302, 303}
    assert saved["sources"][0]["url"] == "https://example.com/a-updated"
    assert saved["sources"][1]["id"] == "airport_b"
    assert saved["sources"][1]["enabled"] is False


def test_groups_save_rejects_overlapping_ranges(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/groups/save",
        data={
            "group_name": ["tg_hk", "browser_us"],
            "group_filter": ["(?i)hk", "(?i)us"],
            "group_exclude": ["(?i)iepl", ""],
            "group_sources": ["", ""],
            "group_start": ["20000", "20009"],
            "group_end": ["20009", "20019"],
        },
    )

    assert response.status_code == 400
    assert "overlap" in response.text.lower()


def test_sources_delete_removes_selected_source(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    client.post(
        "/sources/save",
        data={
            "source_id": ["airport_a", "airport_b"],
            "source_url": ["https://example.com/a", "https://example.com/b"],
            "source_enabled": ["true", "true"],
            "source_format": ["clash", "clash"],
        },
    )

    response = client.post("/sources/delete", data={"delete_index": "0"})
    saved = yaml.safe_load(settings.mapping_path.read_text(encoding="utf-8"))

    assert response.status_code == 200 or response.status_code in {302, 303}
    assert [item["id"] for item in saved["sources"]] == ["airport_b"]


def test_groups_delete_removes_selected_group(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    client.post(
        "/groups/save",
        data={
            "group_name": ["tg_hk", "browser_us"],
            "group_filter": ["(?i)hk", "(?i)us"],
            "group_exclude": ["", ""],
            "group_sources": ["", ""],
            "group_start": ["20000", "21000"],
            "group_end": ["20009", "21009"],
        },
    )

    response = client.post("/groups/delete", data={"delete_index": "1"})
    saved = yaml.safe_load(settings.mapping_path.read_text(encoding="utf-8"))

    assert response.status_code == 200 or response.status_code in {302, 303}
    assert [item["name"] for item in saved["groups"]] == ["tg_hk"]
