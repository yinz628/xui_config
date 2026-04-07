from pathlib import Path

from xui_port_pool_generator.models import SourceConfig
from xui_port_pool_generator.clash_parser import parse_clash_subscription
from xui_port_pool_generator.grouping import group_nodes
from xui_port_pool_generator.models import GroupConfig, PortRange
from xui_port_pool_generator.stable_keys import build_name_affinity_key, build_node_uid
from xui_port_pool_generator.subscriptions import (
    fetch_source_to_cache,
    normalize_file_url_path,
)


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


def test_group_nodes_matches_chinese_region_name_with_abbreviation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.yaml"
    path.write_text(
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

    nodes = parse_clash_subscription("airport_a", path)
    groups = (
        GroupConfig(
            name="tg_hk",
            filter="(?i)hk",
            port_range=PortRange(20000, 20009),
        ),
        GroupConfig(
            name="browser_us",
            filter="(?i)(us|usa)",
            port_range=PortRange(21000, 21009),
        ),
    )

    matched, dropped = group_nodes(nodes, groups)

    assert [name for name, _ in matched] == ["tg_hk", "browser_us"]
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


def test_fetch_source_to_cache_uses_browser_user_agent_for_http(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, str | None] = {"user_agent": None}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b"proxies: []\n"

    def fake_urlopen(request):
        captured["user_agent"] = request.headers.get("User-agent")
        return FakeResponse()

    monkeypatch.setattr("xui_port_pool_generator.subscriptions.urlopen", fake_urlopen)

    source = SourceConfig(
        id="airport_http",
        url="https://example.com/sub",
        format="clash",
        enabled=True,
    )

    target = fetch_source_to_cache(source, tmp_path)

    assert captured["user_agent"] == "Mozilla/5.0"
    assert target.read_text(encoding="utf-8") == "proxies: []\n"
