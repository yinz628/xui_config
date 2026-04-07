from pathlib import Path

from xui_port_pool_generator.allocator import allocate_group_ports
from xui_port_pool_generator.models import GroupConfig, NormalizedNode, PortRange


def make_node(name: str, server: str) -> NormalizedNode:
    return NormalizedNode(
        source_id="airport_a",
        source_path=Path("cache/airport_a.yaml"),
        display_name=name,
        protocol="ss",
        server=server,
        server_port=443,
        raw_proxy={
            "name": name,
            "type": "ss",
            "server": server,
            "port": 443,
            "cipher": "aes-128-gcm",
            "password": "pw",
        },
    )


def test_allocator_reuses_existing_node_uid_binding() -> None:
    matched = [("tg_hk", make_node("HK 01", "hk.example.com"))]
    groups = {
        "tg_hk": GroupConfig(
            name="tg_hk",
            filter="(?i)hk",
            port_range=PortRange(20000, 20001),
        )
    }
    state = {
        "version": 1,
        "groups": {
            "tg_hk": {
                "20000": {
                    "node_uid": "fixed-node",
                    "name_affinity_key": "hk 01",
                    "source_id": "airport_a",
                    "status": "active",
                }
            }
        },
    }

    assigned, issues = allocate_group_ports(
        matched,
        groups,
        state,
        lambda node: "fixed-node",
        lambda _: "hk 01",
    )

    assert assigned[0].port == 20000
    assert issues == []


def test_allocator_reuses_affinity_port_when_node_uid_changes() -> None:
    matched = [("tg_hk", make_node("HK 01", "hk-new.example.com"))]
    groups = {
        "tg_hk": GroupConfig(
            name="tg_hk",
            filter="(?i)hk",
            port_range=PortRange(20000, 20001),
        )
    }
    state = {
        "version": 1,
        "groups": {
            "tg_hk": {
                "20000": {
                    "node_uid": "old-node",
                    "name_affinity_key": "hk 01",
                    "source_id": "airport_a",
                    "status": "inactive",
                }
            }
        },
    }

    assigned, issues = allocate_group_ports(
        matched,
        groups,
        state,
        lambda node: "new-node",
        lambda _: "hk 01",
    )

    assert assigned[0].port == 20000
    assert assigned[0].node_uid == "new-node"
    assert issues == []


def test_allocator_marks_group_capacity_exceeded() -> None:
    matched = [
        ("tg_hk", make_node("HK 01", "a.example.com")),
        ("tg_hk", make_node("HK 02", "b.example.com")),
    ]
    groups = {
        "tg_hk": GroupConfig(
            name="tg_hk",
            filter="(?i)hk",
            port_range=PortRange(20000, 20000),
        )
    }

    assigned, issues = allocate_group_ports(
        matched,
        groups,
        {"version": 1, "groups": {}},
        lambda node: node.server,
        lambda name: name.lower(),
    )

    assert [item.port for item in assigned] == [20000]
    assert issues[0]["reason"] == "group_capacity_exceeded"
