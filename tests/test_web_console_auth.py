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
        json.dumps({"inbounds": [], "outbounds": [], "routing": {"rules": []}}),
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


def test_dashboard_redirects_to_login_when_not_authenticated(
    tmp_path: Path,
) -> None:
    app = create_app(create_workspace(tmp_path))
    client = TestClient(app)

    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/login"


def test_login_sets_session_and_allows_dashboard_access(tmp_path: Path) -> None:
    app = create_app(create_workspace(tmp_path))
    client = TestClient(app)

    login_response = client.post(
        "/login",
        data={"password": "secret-pass"},
        follow_redirects=False,
    )

    assert login_response.status_code in {302, 303}
    assert "session" in login_response.cookies or "set-cookie" in {
        key.lower() for key in login_response.headers.keys()
    }

    dashboard = client.get("/dashboard")

    assert dashboard.status_code == 200
    assert "订阅源快捷编辑" in dashboard.text
