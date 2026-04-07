from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PortRange:
    start: int
    end: int


@dataclass(frozen=True)
class SourceConfig:
    id: str
    url: str
    format: str
    enabled: bool = True


@dataclass(frozen=True)
class GroupConfig:
    name: str
    filter: str
    port_range: PortRange
    exclude: str | None = None
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeConfig:
    cache_dir: str
    state_path: str
    output_path: str
    report_path: str
    output_mode: str
    inbound_listen: str | None = "0.0.0.0"


@dataclass(frozen=True)
class MappingConfig:
    version: int
    sources: tuple[SourceConfig, ...]
    groups: tuple[GroupConfig, ...]
    runtime: RuntimeConfig


@dataclass(frozen=True)
class NormalizedNode:
    source_id: str
    source_path: Path
    display_name: str
    protocol: str
    server: str
    server_port: int
    raw_proxy: dict


@dataclass(frozen=True)
class AssignedNode:
    group_name: str
    port: int
    node_uid: str
    name_affinity_key: str
    node: NormalizedNode
