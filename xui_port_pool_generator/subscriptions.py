from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from .models import SourceConfig


def fetch_source_to_cache(source: SourceConfig, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{source.id}.yaml"
    parsed = urlparse(source.url)
    if parsed.scheme == "file":
        source_path = Path(normalize_file_url_path(parsed.path))
        target.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
        return target
    with urlopen(source.url) as response:
        target.write_bytes(response.read())
    return target


def normalize_file_url_path(raw_path: str) -> str:
    if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
        return raw_path[1:]
    return raw_path
