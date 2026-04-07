from pathlib import Path

import yaml


ROOT = Path(r"F:\x-ui")


def test_compose_generator_service_uses_expected_mounts_and_command() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["generator"]

    assert service["working_dir"] == "/app"
    assert service["command"] == [
        "python",
        "generate_xray_config.py",
        "--mapping",
        "/app/config/mapping.yaml",
        "--template",
        "/app/config/config.json",
    ]
    assert "./config:/app/config" in service["volumes"]
    assert "./data/cache:/app/cache" in service["volumes"]
    assert "./data/state:/app/state" in service["volumes"]
    assert "./output:/app/output" in service["volumes"]


def test_vps_mapping_example_uses_container_runtime_paths() -> None:
    mapping = yaml.safe_load(
        (ROOT / "config" / "mapping.vps.example.yaml").read_text(encoding="utf-8")
    )

    assert mapping["runtime"]["cache_dir"] == "/app/cache"
    assert mapping["runtime"]["state_path"] == "/app/state/port_bindings.json"
    assert mapping["runtime"]["output_path"] == "/app/output/config.generated.json"
    assert mapping["runtime"]["report_path"] == "/app/output/config.generated.report.json"


def test_config_json_example_is_a_real_template_shape() -> None:
    import json

    template = json.loads(
        (ROOT / "config" / "config.json.example").read_text(encoding="utf-8")
    )

    assert "inbounds" in template
    assert "outbounds" in template
