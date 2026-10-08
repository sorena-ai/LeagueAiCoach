"""Map the existing champion tools onto Realtime function definitions."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.assistant.tools import CHAMPION_TOOLS

logger = logging.getLogger(__name__)

_BY_NAME = {tool.name: tool for tool in CHAMPION_TOOLS}


def realtime_tool_definitions() -> list[dict[str, Any]]:
    """JSON tool list for session.update."""
    definitions: list[dict[str, Any]] = []
    for tool in CHAMPION_TOOLS:
        schema = tool.args_schema.model_json_schema()
        definitions.append(
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description or tool.name,
                "parameters": {
                    "type": "object",
                    "properties": schema.get("properties") or {},
                    "required": schema.get("required") or [],
                },
            }
        )
    return definitions


async def run_tool(name: str, arguments: str | dict[str, Any]) -> str:
    """Run one champion tool and return a string the model can speak from."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return "Tool arguments were not valid JSON."
    else:
        args = arguments
    try:
        result = await asyncio.to_thread(tool.invoke, args)
    except Exception:
        logger.exception("Realtime tool %s failed", name)
        return f"The {name} lookup failed."
    text = result if isinstance(result, str) else json.dumps(result)
    # Keep tool payloads bounded so one lookup cannot fill the voice context.
    if len(text) > 12000:
        return text[:12000] + "\n[truncated]"
    return text
