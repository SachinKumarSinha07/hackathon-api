"""Tool definitions for the chat assistant's LLM tool-calling integration."""

from typing import Any, Dict, List

from app.api.models.vulnerability_master import VulnerabilityMaster

CHAT_TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "aggregate_vulnerabilities",
                "description": (
                    "Count vulnerabilities grouped by a field. Returns an array of "
                    "{name, value} objects sorted by count descending. Use this when "
                    "the user asks for breakdowns, distributions, or grouped counts."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "group_by": {
                                "type": "string",
                                "enum": [
                                    "severity",
                                    "dev_status",
                                    "verification",
                                    "project",
                                    "pic",
                                ],
                                "description": "The field to group by.",
                            }
                        },
                        "required": ["group_by"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "render_visualization",
                "description": (
                    "Render data as an interactive chart or table in the user's chat UI. "
                    "Call this after aggregating data when a visual would be clearer than text. "
                    "Use 'bar' for comparisons/rankings, 'pie' for proportions, "
                    "'table' for multi-column detail."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["bar", "pie", "table"],
                            },
                            "title": {
                                "type": "string",
                                "description": "Short title for the chart or table.",
                            },
                            "data": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": (
                                    "For bar/pie: [{\"name\": \"label\", \"value\": number}]. "
                                    "For table: [{\"col1\": \"v\", \"col2\": \"v\", ...}]."
                                ),
                            },
                        },
                        "required": ["type", "title", "data"],
                    }
                },
            }
        },
    ]
}

VISUALIZATION_TOOL_NAME = "render_visualization"


def aggregate_records(
    records: List[VulnerabilityMaster], group_by: str
) -> List[Dict[str, Any]]:
    """Count records grouped by a field, sorted descending by count."""
    counts: Dict[str, int] = {}
    for r in records:
        if group_by == "project":
            key = r.project.project_name if r.project else "Unknown"
        else:
            key = getattr(r, group_by, None) or "Unknown"
        counts[key] = counts.get(key, 0) + 1
    return [
        {"name": k, "value": v}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]
