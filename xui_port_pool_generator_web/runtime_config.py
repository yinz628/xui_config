import json
from datetime import datetime
from pathlib import Path

import yaml

from xui_port_pool_generator.mapping_loader import load_mapping


def load_runtime_file_metadata(path: Path) -> dict:
    exists = path.exists()
    stat = path.stat() if exists else None
    return {
        "path": str(path),
        "exists": exists,
        "size": stat.st_size if stat else None,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        if stat
        else None,
        "text": path.read_text(encoding="utf-8") if exists else "",
    }


def validate_mapping_yaml(text: str) -> dict:
    temp = yaml.safe_load(text)
    if temp is None:
        raise ValueError("mapping.yaml 不能为空")
    temp_path = Path(".runtime_config_mapping_check.yaml")
    try:
        temp_path.write_text(text, encoding="utf-8")
        load_mapping(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return temp


def validate_template_json(text: str) -> dict:
    data = json.loads(text)
    missing = [key for key in ("inbounds", "outbounds") if key not in data]
    if missing:
        raise ValueError(f"config.json 缺少必要字段: {', '.join(missing)}")
    return data
