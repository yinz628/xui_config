import re

from .models import GroupConfig, NormalizedNode


def group_nodes(
    nodes: list[NormalizedNode],
    groups: tuple[GroupConfig, ...],
) -> tuple[list[tuple[str, NormalizedNode]], list[dict]]:
    matched: list[tuple[str, NormalizedNode]] = []
    dropped: list[dict] = []
    for node in nodes:
        selected_group: str | None = None
        for group in groups:
            if not re.search(group.filter, node.display_name):
                continue
            if group.exclude and re.search(group.exclude, node.display_name):
                continue
            selected_group = group.name
            break
        if selected_group is None:
            dropped.append({"node": node.display_name, "reason": "group_not_matched"})
            continue
        matched.append((selected_group, node))
    return matched, dropped
