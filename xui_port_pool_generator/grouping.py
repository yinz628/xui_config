import re
import unicodedata

from .models import GroupConfig, NormalizedNode


REGION_ALIAS_MAP: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("香港", "hong kong", "🇭🇰"), ("hk", "hong kong")),
    (("美国", "美國", "united states", "🇺🇸"), ("us", "usa", "united states")),
    (("日本", "japan", "🇯🇵"), ("jp", "japan")),
    (("台湾", "台灣", "taiwan", "🇹🇼"), ("tw", "taiwan")),
    (("新加坡", "singapore", "🇸🇬"), ("sg", "singapore")),
    (("韩国", "韓國", "korea", "south korea", "🇰🇷"), ("kr", "korea", "south korea")),
    (("英国", "英國", "united kingdom", "britain", "🇬🇧"), ("uk", "gb", "united kingdom")),
    (("德国", "德國", "germany", "🇩🇪"), ("de", "germany")),
    (("法国", "法國", "france", "🇫🇷"), ("fr", "france")),
    (("加拿大", "canada", "🇨🇦"), ("ca", "canada")),
    (("澳大利亚", "澳洲", "australia", "🇦🇺"), ("au", "australia")),
)


def group_nodes(
    nodes: list[NormalizedNode],
    groups: tuple[GroupConfig, ...],
) -> tuple[list[tuple[str, NormalizedNode]], list[dict]]:
    matched: list[tuple[str, NormalizedNode]] = []
    dropped: list[dict] = []
    for node in nodes:
        selected_group: str | None = None
        match_text = build_match_text(node.display_name)
        for group in groups:
            if not re.search(group.filter, match_text):
                continue
            if group.exclude and re.search(group.exclude, match_text):
                continue
            selected_group = group.name
            break
        if selected_group is None:
            dropped.append({"node": node.display_name, "reason": "group_not_matched"})
            continue
        matched.append((selected_group, node))
    return matched, dropped


def build_match_text(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", display_name).lower()
    aliases: list[str] = []
    for keys, alias_values in REGION_ALIAS_MAP:
        if any(key.lower() in normalized for key in keys):
            aliases.extend(alias_values)
    if not aliases:
        return display_name
    return f"{display_name}\n{' '.join(sorted(set(aliases)))}"
