from pathlib import Path

from xui_port_pool_generator.clash_parser import parse_clash_subscription
from xui_port_pool_generator.grouping import group_nodes
from xui_port_pool_generator.models import GroupConfig, PortRange
from xui_port_pool_generator.stable_keys import build_name_affinity_key, build_node_uid
from xui_port_pool_generator.subscriptions import normalize_file_url_path


def test_random_filename_does_not_change_source_identity(tmp_path: Path) -> None:
    path = tmp_path / "RH5SFz15rrci.yaml"
    path.write_text(
        """
proxies:
  - name: HK 01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
""".strip(),
        encoding="utf-8",
    )

    node = parse_clash_subscription("airport_a", path)[0]

    assert node.source_id == "airport_a"
    assert node.source_path.name == "RH5SFz15rrci.yaml"
    assert build_name_affinity_key("🇭🇰   HK 01") == "hk 01"
    assert len(build_node_uid(node)) == 24


def test_group_nodes_uses_first_match_wins_and_exclude(tmp_path: Path) -> None:
    path = tmp_path / "source.yaml"
    path.write_text(
        """
proxies:
  - name: HK IEPL 01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
""".strip(),
        encoding="utf-8",
    )

    node = parse_clash_subscription("airport_a", path)[0]
    groups = (
        GroupConfig(
            name="tg_hk",
            filter="(?i)hk",
            exclude="(?i)iepl",
            port_range=PortRange(20000, 20009),
        ),
        GroupConfig(
            name="fallback_hk",
            filter="(?i)hk",
            port_range=PortRange(20010, 20019),
        ),
    )

    matched, dropped = group_nodes([node], groups)

    assert [name for name, _ in matched] == ["fallback_hk"]
    assert dropped == []


def test_normalize_file_url_path_preserves_posix_absolute_paths() -> None:
    assert (
        normalize_file_url_path("/app/config/subscriptions/310config86-106.yaml")
        == "/app/config/subscriptions/310config86-106.yaml"
    )


def test_normalize_file_url_path_strips_windows_drive_prefix_slash() -> None:
    assert normalize_file_url_path("/F:/x-ui/310config86-106.yaml") == (
        "F:/x-ui/310config86-106.yaml"
    )
