from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from .models import SourceConfig


def fetch_source_to_cache(source: SourceConfig, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{source.id}.yaml"
    parsed = urlparse(source.url)
    if parsed.scheme == "file":
        source_path = Path(parsed.path.lstrip("/"))
        target.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
        return target
    with urlopen(source.url) as response:
        target.write_bytes(response.read())
    return target
