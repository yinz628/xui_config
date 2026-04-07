from datetime import datetime, timezone

from .models import AssignedNode, MappingConfig, NormalizedNode


def build_report(
    mapping: MappingConfig,
    matched: list[tuple[str, NormalizedNode]],
    assigned: list[AssignedNode],
    issues: list[dict],
) -> dict:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "source_count": len(mapping.sources),
            "group_count": len(mapping.groups),
            "matched_count": len(matched),
            "assigned_count": len(assigned),
            "issue_count": len(issues),
        },
        "issues": issues,
    }
