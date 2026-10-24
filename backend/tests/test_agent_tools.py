"""Tool registry and argument validation shared by the LangChain agent."""

import json

from llm import build_tools, execute_tool
from tool_schemas import TOOL_FUNCTIONS, TOOLS


def test_every_schema_has_a_function():
    names = [tool["function"]["name"] for tool in TOOLS]
    assert len(names) == len(set(names)) == 26
    assert set(names) == set(TOOL_FUNCTIONS)
    assert len(build_tools()) == 26


def test_execute_tool_runs_a_valid_call():
    result = execute_tool("get_order_status", json.dumps({"order_id": "ORD-002"}))
    assert result["status"] == "ok"


def test_execute_tool_rejects_bad_arguments():
    assert execute_tool("get_order_status", json.dumps({"order_id": "ORD-002", "x": 1}))["status"] == "error"
    assert execute_tool("get_stage_output", json.dumps(
        {"stage": "DYEING", "production_date": "2026-03-31"}))["status"] == "error"
    assert execute_tool("delete_everything", "{}")["status"] == "error"


def test_required_parameters_are_declared():
    for tool in TOOLS:
        parameters = tool["function"]["parameters"]
        assert set(parameters["required"]) <= set(parameters["properties"]), tool["function"]["name"]


def test_a_tool_bug_is_reported_as_internal_not_as_missing_data(monkeypatch, caplog):
    # A KeyError inside a tool is a bug; the model must not be told the factory data is unreadable.
    def broken(order_id):
        return {}["missing"]

    monkeypatch.setitem(TOOL_FUNCTIONS, "get_order_status", broken)
    with caplog.at_level("ERROR", logger="llm"):
        result = execute_tool("get_order_status", json.dumps({"order_id": "ORD-002"}))
    assert result["status"] == "error"
    assert result["message"].startswith("Internal tool error")
    assert "Tool get_order_status failed" in caplog.text


def test_unreadable_data_is_still_reported_as_such(monkeypatch):
    def unreadable(order_id):
        raise FileNotFoundError("orders.csv")

    monkeypatch.setitem(TOOL_FUNCTIONS, "get_order_status", unreadable)
    result = execute_tool("get_order_status", json.dumps({"order_id": "ORD-002"}))
    assert result == {"status": "error", "message": "Could not read the factory data."}
