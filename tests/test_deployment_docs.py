from pathlib import Path


ROOT = Path(r"F:\x-ui")


def test_deploy_readme_and_env_example_cover_required_commands() -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme_text = (ROOT / "README-deploy.md").read_text(encoding="utf-8")

    assert "SMOKE_SSH_HOST" in env_text
    assert "SMOKE_SSH_USER" in env_text
    assert "SMOKE_REMOTE_PATH" in env_text
    assert "docker compose build" in readme_text
    assert "docker compose run --rm generator" in readme_text
    assert "/opt/xui-config/output" in readme_text
