import json
from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from xui_port_pool_generator_web.app import AppSettings, create_app


def create_workspace(tmp_path: Path) -> AppSettings:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    config_dir.mkdir()
    (data_dir / "state").mkdir(parents=True)
    output_dir.mkdir()
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

    (config_dir / "mapping.yaml").write_text(
        f"""
version: 1
sources:
  - id: airport_a
    url: file:///{source_path.as_posix()}
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
    (output_dir / "nodes.snapshot.json").write_text(
        json.dumps(
            {
                "summary": {"node_count": 2, "matched_count": 1, "assigned_count": 1},
                "items": [
                    {
                        "node_uid": "node-hk",
                        "display_name": "香港 IEPL 01",
                        "source_id": "airport_a",
                        "protocol": "ss",
                        "server": "hk.example.com",
                        "server_port": 443,
                        "region_tags": ["hk"],
                        "matched_group": "tg_hk",
                        "assigned_port": 20000,
                    },
                    {
                        "node_uid": "node-us",
                        "display_name": "美国家宽 01",
                        "source_id": "airport_a",
                        "protocol": "ss",
                        "server": "us.example.com",
                        "server_port": 443,
                        "region_tags": ["us"],
                        "matched_group": None,
                        "assigned_port": None,
                    },
                ],
            }
        ),
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


def test_groups_builder_page_shows_region_tags_from_latest_snapshot(
    tmp_path: Path,
) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.get("/groups/tg_hk/builder")

    assert response.status_code == 200
    assert "地区标签" in response.text
    assert "hk" in response.text
    assert "us" in response.text
    assert "香港 IEPL 01" in response.text


def test_groups_page_exposes_builder_open_action_for_editable_rows(
    tmp_path: Path,
) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.get("/groups")

    assert response.status_code == 200
    assert "/groups/builder/open" in response.text
    assert "规则生成器" in response.text


def test_groups_builder_open_saves_current_form_and_redirects(
    tmp_path: Path,
) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/groups/builder/open",
        data={
            "group_name": ["tg_hk", "browser_us"],
            "group_filter": ["(?i)hk", "(?i)us"],
            "group_exclude": ["", ""],
            "group_sources": ["", ""],
            "group_start": ["20000", "21000"],
            "group_end": ["20009", "21009"],
            "builder_index": "1",
        },
        follow_redirects=False,
    )

    saved = yaml.safe_load(settings.mapping_path.read_text(encoding="utf-8"))

    assert response.status_code in {302, 303}
    assert response.headers["location"] == "/groups/browser_us/builder#builder-panel"
    assert [item["name"] for item in saved["groups"]] == ["tg_hk", "browser_us"]


def test_rule_builder_saves_regions_and_manual_overrides(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/groups/tg_hk/builder/save",
        data={
            "include_regions": ["hk", "us"],
            "exclude_regions": ["tw"],
            "manual_include_nodes": ["node-us"],
            "manual_exclude_nodes": ["node-hk"],
        },
    )

    saved = yaml.safe_load(settings.mapping_path.read_text(encoding="utf-8"))

    assert response.status_code == 200 or response.status_code in {302, 303}
    assert saved["groups"][0]["include_regions"] == ["hk", "us"]
    assert saved["groups"][0]["exclude_regions"] == ["tw"]
    assert saved["groups"][0]["manual_include_nodes"] == ["node-us"]
    assert saved["groups"][0]["manual_exclude_nodes"] == ["node-hk"]
