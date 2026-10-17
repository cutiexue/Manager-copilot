"""Tool registry and argument validation shared by the LangChain agent."""

import json

from llm import build_tools, execute_tool
from tool_schemas import TOOL_FUNCTIONS, TOOLS


def test_every_schema_has_a_function():
    names = [tool["function"]["name"] for tool in TOOLS]
    assert len(names) == len(set(names)) == 21
    assert set(names) == set(TOOL_FUNCTIONS)
    assert len(build_tools()) == 21


def test_execute_tool_runs_a_valid_call():
    result = execute_tool("get_order_status", json.dumps({"order_id": "ORD-002"}))
    assert result["status"] == "ok"


def test_execute_tool_rejects_bad_arguments():
    assert execute_tool("get_order_status", json.dumps({"order_id": "ORD-002", "x": 1}))["status"] == "error"
    assert execute_tool("get_stage_output", json.dumps(
        {"stage": "DYEING", "production_date": "2026-03-31"}))["status"] == "error"
    assert execute_tool("delete_everything", "{}")["status"] == "error"
