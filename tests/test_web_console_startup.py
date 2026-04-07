import sys
from pathlib import Path

import pytest

ROOT = Path(r"F:\x-ui")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xui_port_pool_generator_web.app import AppSettings, create_app


def test_create_app_rejects_placeholder_credentials(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WEB_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("WEB_ADMIN_PASSWORD", "__CHANGE_ME__")
    monkeypatch.setenv("WEB_SESSION_SECRET", "__GENERATE_A_LONG_RANDOM_SECRET__")

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_still_accepts_explicit_settings(tmp_path: Path) -> None:
    settings = AppSettings(
        base_dir=tmp_path,
        mapping_path=tmp_path / "mapping.yaml",
        template_path=tmp_path / "config.json",
        workdir=tmp_path,
        admin_password="secret-pass",
        session_secret="session-secret",
    )

    app = create_app(settings)

    assert app.title == "X-UI 中文控制台"
