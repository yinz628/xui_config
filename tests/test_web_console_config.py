from pathlib import Path

import json
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
    source_path = tmp_path / "source.yaml"
    source_path.write_text(
        """
proxies:
  - name: HK BASE
    type: ss
    server: hk-base.example.com
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


def test_groups_save_reports_missing_ports_instead_of_500(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/groups/save",
        data={
            "group_name": ["tg_hk", "browser_us"],
            "group_filter": ["(?i)hk", "(?i)us"],
            "group_exclude": ["", ""],
            "group_sources": ["", ""],
            "group_start": ["20000", ""],
            "group_end": ["20009", ""],
        },
    )

    assert response.status_code == 400
    assert "端口" in response.text


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


def test_sources_save_refreshes_snapshot_and_clears_stale_generated_files(
    tmp_path: Path,
) -> None:
    settings = create_workspace(tmp_path)
    source_a = tmp_path / "source_a.yaml"
    source_b = tmp_path / "source_b.yaml"
    source_a.write_text(
        """
proxies:
  - name: HK OLD
    type: ss
    server: hk-old.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
""".strip(),
        encoding="utf-8",
    )
    source_b.write_text(
        """
proxies:
  - name: HK NEW
    type: ss
    server: hk-new.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "output" / "nodes.snapshot.json").write_text(
        json.dumps(
            {
                "summary": {"node_count": 1, "matched_count": 1, "assigned_count": 1},
                "items": [
                    {
                        "node_uid": "old-node",
                        "display_name": "OLD NODE",
                        "source_id": "airport_a",
                        "protocol": "ss",
                        "server": "old.example.com",
                        "server_port": 443,
                        "region_tags": ["hk"],
                        "matched_group": "tg_hk",
                        "assigned_port": 20000,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "output" / "config.generated.json").write_text("{}", encoding="utf-8")
    (tmp_path / "output" / "config.generated.report.json").write_text(
        '{"summary":{"assigned_count":1}}',
        encoding="utf-8",
    )
    (tmp_path / "data" / "state" / "port_bindings.json").write_text(
        '{"groups":{"tg_hk":{"20000":"old-node"}}}',
        encoding="utf-8",
    )

    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/sources/save",
        data={
            "source_id": ["airport_a"],
            "source_url": [f"file:///{source_b.as_posix()}"],
            "source_enabled": ["true"],
            "source_format": ["clash"],
        },
        follow_redirects=False,
    )

    snapshot = json.loads(
        (tmp_path / "output" / "nodes.snapshot.json").read_text(encoding="utf-8")
    )

    assert response.status_code in {302, 303}
    assert [item["display_name"] for item in snapshot["items"]] == ["HK NEW"]
    assert not (tmp_path / "output" / "config.generated.json").exists()
    assert not (tmp_path / "output" / "config.generated.report.json").exists()
    assert not (tmp_path / "data" / "state" / "port_bindings.json").exists()


def test_sources_delete_removes_deleted_source_nodes_from_snapshot(
    tmp_path: Path,
) -> None:
    settings = create_workspace(tmp_path)
    source_a = tmp_path / "source_a.yaml"
    source_b = tmp_path / "source_b.yaml"
    source_a.write_text(
        """
proxies:
  - name: HK A
    type: ss
    server: hk-a.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
""".strip(),
        encoding="utf-8",
    )
    source_b.write_text(
        """
proxies:
  - name: HK B
    type: ss
    server: hk-b.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app(settings))
    login(client)
    client.post(
        "/sources/save",
        data={
            "source_id": ["airport_a", "airport_b"],
            "source_url": [
                f"file:///{source_a.as_posix()}",
                f"file:///{source_b.as_posix()}",
            ],
            "source_enabled": ["true", "true"],
            "source_format": ["clash", "clash"],
        },
        follow_redirects=False,
    )

    response = client.post("/sources/delete", data={"delete_index": "0"})
    snapshot = json.loads(
        (tmp_path / "output" / "nodes.snapshot.json").read_text(encoding="utf-8")
    )

    assert response.status_code == 200 or response.status_code in {302, 303}
    assert [item["source_id"] for item in snapshot["items"]] == ["airport_b"]
