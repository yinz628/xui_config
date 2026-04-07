from pathlib import Path

import yaml

from .models import GroupConfig, MappingConfig, PortRange, RuntimeConfig, SourceConfig


def load_mapping(path: Path) -> MappingConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = tuple(
        GroupConfig(
            name=item["name"],
            filter=item.get("filter", ""),
            exclude=item.get("exclude"),
            source_ids=tuple(item.get("source_ids", ())),
            include_regions=tuple(item.get("include_regions", ())),
            exclude_regions=tuple(item.get("exclude_regions", ())),
            manual_include_nodes=tuple(item.get("manual_include_nodes", ())),
            manual_exclude_nodes=tuple(item.get("manual_exclude_nodes", ())),
            filter_regex=item.get("filter_regex", ""),
            exclude_regex=item.get("exclude_regex", ""),
            port_range=PortRange(**item["port_range"]),
        )
        for item in raw["groups"]
    )
    _validate_ranges(groups)
    sources = tuple(
        SourceConfig(
            id=item["id"],
            url=item["url"],
            format=item["format"],
            enabled=item.get("enabled", True),
        )
        for item in raw["sources"]
    )
    return MappingConfig(
        version=raw["version"],
        sources=sources,
        groups=groups,
        runtime=RuntimeConfig(
            cache_dir=raw["runtime"]["cache_dir"],
            state_path=raw["runtime"]["state_path"],
            output_path=raw["runtime"]["output_path"],
            report_path=raw["runtime"]["report_path"],
            output_mode=raw["runtime"]["output_mode"],
            inbound_listen=raw["runtime"].get("inbound_listen", "0.0.0.0"),
        ),
    )


def _validate_ranges(groups: tuple[GroupConfig, ...]) -> None:
    occupied: set[int] = set()
    for group in groups:
        for port in range(group.port_range.start, group.port_range.end + 1):
            if port in occupied:
                raise ValueError(f"port range overlap detected at {port}")
            occupied.add(port)
