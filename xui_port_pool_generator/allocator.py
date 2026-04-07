from .models import AssignedNode, GroupConfig, NormalizedNode


def allocate_group_ports(
    matched: list[tuple[str, NormalizedNode]],
    groups_by_name: dict[str, GroupConfig],
    state: dict,
    node_uid_factory,
    affinity_factory,
) -> tuple[list[AssignedNode], list[dict]]:
    assigned: list[AssignedNode] = []
    issues: list[dict] = []
    used_ports_by_group: dict[str, set[int]] = {}

    for group_name, node in matched:
        group = groups_by_name[group_name]
        history = state.setdefault("groups", {}).setdefault(group_name, {})
        used_ports = used_ports_by_group.setdefault(group_name, set())
        node_uid = node_uid_factory(node)
        affinity_key = affinity_factory(node.display_name)

        port = _find_existing_port(history, node_uid, used_ports)
        if port is None:
            port = _find_affinity_port(history, affinity_key, used_ports)
        if port is None:
            port = _find_smallest_free_port(
                group.port_range.start,
                group.port_range.end,
                history,
                used_ports,
            )
        if port is None:
            issues.append(
                {
                    "group_name": group_name,
                    "node_name": node.display_name,
                    "reason": "group_capacity_exceeded",
                }
            )
            continue

        used_ports.add(port)
        history[str(port)] = {
            "node_uid": node_uid,
            "name_affinity_key": affinity_key,
            "source_id": node.source_id,
            "status": "active",
        }
        assigned.append(
            AssignedNode(
                group_name=group_name,
                port=port,
                node_uid=node_uid,
                name_affinity_key=affinity_key,
                node=node,
            )
        )

    return assigned, issues


def _find_existing_port(
    history: dict[str, dict],
    node_uid: str,
    used_ports: set[int],
) -> int | None:
    for port_text, binding in history.items():
        port = int(port_text)
        if port in used_ports:
            continue
        if binding.get("node_uid") == node_uid:
            return port
    return None


def _find_affinity_port(
    history: dict[str, dict],
    affinity_key: str,
    used_ports: set[int],
) -> int | None:
    for port_text, binding in history.items():
        port = int(port_text)
        if port in used_ports:
            continue
        if binding.get("name_affinity_key") == affinity_key:
            return port
    return None


def _find_smallest_free_port(
    start: int,
    end: int,
    history: dict[str, dict],
    used_ports: set[int],
) -> int | None:
    occupied = {int(port_text) for port_text in history} | used_ports
    for port in range(start, end + 1):
        if port not in occupied:
            return port
    return None
