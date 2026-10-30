"""
Pydantic schemas for POST /api/tasks/{task_id}/tools/{tool_name}.

The request body is a raw dict validated against the specific tool's own
input model inside app.tools.registry.run_tool() — this schema only wraps
that dict, since the shape genuinely differs per tool (read_file vs.
modify_file vs. git_diff all take different fields).
"""
from typing import Any

from pydantic import BaseModel


class ToolInvokeRequest(BaseModel):
    # repository_id is intentionally NOT included separately — every
    # tool's own input model already requires it, so validation happens
    # once, inside app.tools.registry.run_tool(), against the correct
    # per-tool schema.
    input: dict[str, Any]


class ToolInvokeResponse(BaseModel):
    tool_name: str
    output: dict[str, Any]


class ToolDescriptor(BaseModel):
    name: str
    description: str


class ToolListResponse(BaseModel):
    tools: list[ToolDescriptor]
