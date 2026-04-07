import json
from pathlib import Path

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


def test_generate_run_calls_pipeline_and_shows_summary(
    tmp_path: Path, monkeypatch
) -> None:
    settings = create_workspace(tmp_path)

    def fake_run_pipeline(mapping_path: Path, template_path: Path, workdir: Path) -> dict:
        (workdir / "output").mkdir(exist_ok=True)
        (workdir / "data" / "state").mkdir(parents=True, exist_ok=True)
        (workdir / "output" / "config.generated.report.json").write_text(
            json.dumps({"summary": {"assigned_count": 7, "issue_count": 2}, "issues": []}),
            encoding="utf-8",
        )
        (workdir / "data" / "state" / "port_bindings.json").write_text(
            json.dumps({"groups": {"tg_hk": {"20000": {"node_uid": "abc"}}}}),
            encoding="utf-8",
        )
        return {"summary": {"assigned_count": 7, "issue_count": 2}}

    monkeypatch.setattr("xui_port_pool_generator_web.app.run_pipeline", fake_run_pipeline)

    client = TestClient(create_app(settings))
    login(client)

    response = client.post("/generate/run", follow_redirects=True)

    assert response.status_code == 200
    assert "已分配数量" in response.text
    assert "7" in response.text
    assert "config.generated.json" in response.text
    assert "config.generated.report.json" in response.text
    assert "port_bindings.json" in response.text


def test_dashboard_save_and_generate_updates_sources_then_runs_pipeline(
    tmp_path: Path, monkeypatch
) -> None:
    settings = create_workspace(tmp_path)
    calls: list[str] = []

    def fake_run_pipeline(mapping_path: Path, template_path: Path, workdir: Path) -> dict:
        calls.append(mapping_path.read_text(encoding="utf-8"))
        (workdir / "output").mkdir(exist_ok=True)
        (workdir / "data" / "state").mkdir(parents=True, exist_ok=True)
        (workdir / "output" / "config.generated.report.json").write_text(
            json.dumps({"summary": {"assigned_count": 1, "issue_count": 0}, "issues": []}),
            encoding="utf-8",
        )
        (workdir / "data" / "state" / "port_bindings.json").write_text(
            json.dumps({"groups": {"tg_hk": {"20000": {"node_uid": "abc"}}}}),
            encoding="utf-8",
        )
        return {"summary": {"assigned_count": 1, "issue_count": 0}}

    monkeypatch.setattr("xui_port_pool_generator_web.app.run_pipeline", fake_run_pipeline)

    client = TestClient(create_app(settings))
    login(client)

    response = client.post(
        "/dashboard/sources/save-and-generate",
        data={
            "source_id": ["airport_a"],
            "source_url": ["https://example.com/new-a"],
            "source_enabled": ["true"],
            "source_format": ["clash"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "生成已完成。" in response.text
    assert "https://example.com/new-a" in calls[0]


def test_reports_page_reads_report_and_state_files(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    (tmp_path / "output" / "config.generated.report.json").write_text(
        json.dumps(
            {
                "summary": {"assigned_count": 4, "issue_count": 1},
                "issues": [{"reason": "group_not_matched"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "data" / "state" / "port_bindings.json").write_text(
        json.dumps({"groups": {"tg_hk": {"20000": {"node_uid": "abc"}}}}),
        encoding="utf-8",
    )

    client = TestClient(create_app(settings))
    login(client)

    response = client.get("/reports")

    assert response.status_code == 200
    assert "group_not_matched" in response.text
    assert "未命中任何分组规则" in response.text
    assert "tg_hk" in response.text
    assert "20000" in response.text


def test_download_routes_serve_generated_artifacts(tmp_path: Path) -> None:
    settings = create_workspace(tmp_path)
    (tmp_path / "output" / "config.generated.json").write_text(
        '{"inbounds":[]}',
        encoding="utf-8",
    )
    (tmp_path / "output" / "config.generated.report.json").write_text(
        '{"summary":{"assigned_count":1},"issues":[]}',
        encoding="utf-8",
    )
    (tmp_path / "data" / "state" / "port_bindings.json").write_text(
        '{"groups":{"tg_hk":{"20000":{"node_uid":"abc"}}}}',
        encoding="utf-8",
    )

    client = TestClient(create_app(settings))
    login(client)

    config_response = client.get("/downloads/config")
    report_response = client.get("/downloads/report")
    state_response = client.get("/downloads/state")

    assert config_response.status_code == 200
    assert report_response.status_code == 200
    assert state_response.status_code == 200
    assert "inbounds" in config_response.text
    assert "assigned_count" in report_response.text
    assert "tg_hk" in state_response.text
