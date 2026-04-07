from pathlib import Path


ROOT = Path(r"F:\x-ui")


def test_smoke_defaults_target_compose_deployment_root() -> None:
    text = (ROOT / "scripts" / "test_smoke_connection.py").read_text(encoding="utf-8")

    assert 'DEFAULT_REMOTE_PATH = "/opt/xui-config"' in text


def test_build_summary_command_checks_new_layout_and_runs_generator() -> None:
    text = (ROOT / "scripts" / "test_smoke_connection.py").read_text(encoding="utf-8")

    assert "docker compose run --rm generator" in text
    assert "config/mapping.yaml" in text
    assert "config/config.json" in text
    assert "data/state/port_bindings.json" in text
    assert "output/config.generated.report.json" in text
