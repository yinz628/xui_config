import hashlib
import json
import re
import unicodedata

from .models import NormalizedNode


def build_name_affinity_key(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", display_name).lower()
    normalized = re.sub(r"[\U0001F1E6-\U0001F1FF]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def build_node_uid(node: NormalizedNode) -> str:
    payload = {
        "source_id": node.source_id,
        "protocol": node.protocol,
        "server": node.server,
        "server_port": node.server_port,
        "auth": {
            "cipher": node.raw_proxy.get("cipher"),
            "password": node.raw_proxy.get("password"),
            "uuid": node.raw_proxy.get("uuid"),
        },
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return digest[:24]
