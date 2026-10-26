"""Read-only API views (plan §11): an order, a stage's output, feasibility estimates, one source row.

They must give the same numbers as the agent's tools, and refuse bad input with a readable 400.
"""

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import create_app
from llm import execute_tool
from service import ChatService
from storage import SQLiteStore
from tool_schemas import ESTIMATION_FUNCTIONS
from tools import compare_stage_output, trace_order

DATA = Path(__file__).resolve().parents[1] / "track1" / "data"


class NoAgent:
    def invoke(self, state, config):
        raise AssertionError("read-only views must not call the model")


@pytest.fixture
def setup(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    service = ChatService(store, agent=NoAgent())
    return TestClient(create_app(service)), service.actions


def csv_line(name, line):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    return dict(zip(rows[0], rows[line - 1]))


def test_order_detail_matches_the_agent_tool_in_any_spelling(setup):
    client, _ = setup
    for spelling in ("ORD-062", "ord062", "62"):
        body = client.get(f"/orders/{spelling}").json()
        assert body["order_id"] == "ORD-062"
        assert body["trace"] == trace_order("ORD-062")
    # Every cited row comes back exactly as it is in the CSV.
    for key, row in body["evidence"]["rows"].items():
        source, line = key.split("#")
        assert row == csv_line(Path(source).name, int(line))
    assert {"source": "track1/data/orders.csv", "row": 110, "key": "ORD-062", "id": "orders.csv:110"} in body["evidence"]["refs"]
    for ref in body["evidence"]["refs"]:  # every id resolves to the same row
        assert client.get(f"/evidence/{ref['id']}").json()["data"] == body["evidence"]["rows"][f"{ref['source']}#{ref['row']}"]


def test_order_detail_lists_its_saved_follow_ups(setup):
    client, actions = setup
    note = actions.propose("note", {"order_id": "ord-062", "text": "Customer asked for photos."}, "ui")
    actions.confirm(note["id"])
    other = actions.propose("note", {"order_id": "ORD-107", "text": "Not this one."}, "ui")
    actions.confirm(other["id"])
    follow_ups = client.get("/orders/ORD-062").json()["follow_ups"]
    assert [n["text"] for n in follow_ups["notes"]] == ["Customer asked for photos."]
    assert follow_ups["reminders"] == [] and follow_ups["watches"] == []


def test_unknown_order_is_404_with_candidates(setup):
    client, _ = setup
    response = client.get("/orders/bright")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND" and body["candidates"]
    assert all(c.startswith("ORD-") for c in body["candidates"])
    # No close match: still a clean 404, without an empty candidate list.
    assert client.get("/orders/ORD-9999").json() == {"detail": "No order 'ORD-9999' in the data.", "code": "NOT_FOUND"}


def test_stage_output_defaults_to_the_last_workday(setup):
    client, _ = setup
    body = client.get("/production/stages/assembly").json()
    assert body["date"] == "2026-03-31" and body["stage"] == "ASSEMBLY"
    assert body["comparison"] == compare_stage_output("ASSEMBLY", "2026-03-31", 7)
    series = body["series"]
    assert len(series) == 10 and series[-1]["date"] == "2026-03-31"
    assert "2026-03-29" not in [p["date"] for p in series]  # Sunday is not a workday
    for point in series:
        assert point["pieces_completed"] == int(csv_line("production_log.csv", point["source_row"])["pieces_completed"])


def test_stage_output_on_a_sunday_and_outside_the_data(setup):
    client, _ = setup
    sunday = client.get("/production/stages/ASSEMBLY", params={"date": "2026-03-29"}).json()
    assert sunday["status"] == "not_applicable" and sunday["series"][-1]["date"] == "2026-03-28"
    after = client.get("/production/stages/ASSEMBLY", params={"date": "2026-04-05"})
    assert after.status_code == 404 and after.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize("path", [
    "/production/stages/paint",
    "/production/stages/ASSEMBLY?date=31-03-2026",
    "/production/stages/ASSEMBLY?days=0",
    "/production/stages/ASSEMBLY?days=78",
    "/production/stages/ASSEMBLY?baseline_days=0",
    "/production/stages/ASSEMBLY?baseline_days=x",
])
def test_stage_output_rejects_bad_input(setup, path):
    client, _ = setup
    response = client.get(path)
    assert response.status_code == 400 and response.json()["code"] == "INVALID_REQUEST"


def test_feasibility_runs_the_agents_estimators(setup):
    client, _ = setup
    names = [e["name"] for e in client.get("/feasibility/estimators").json()]
    assert names == list(ESTIMATION_FUNCTIONS)
    arguments = {"pieces": 500}
    body = client.post("/feasibility/estimate", json={"estimator": "estimate_in_house", "arguments": arguments}).json()
    assert body["result"] == execute_tool("estimate_in_house", json.dumps(arguments))
    assert body["result"]["completion_date"] == "2026-05-30"  # behind the unfinished orders (C-1)
    assert body["result"]["queue_basis"] == "open_orders"
    assert body["evidence"]["refs"]  # the baseline rows behind the estimate


@pytest.mark.parametrize("payload", [
    {"estimator": "estimate_in_house", "arguments": {"pieces": -1}},
    {"estimator": "estimate_in_house", "arguments": {"pieces": 2_000_000}},
    {"estimator": "estimate_in_house", "arguments": {}},
    {"estimator": "estimate_in_house", "arguments": {"pieces": 5, "admin": True}},
    {"estimator": "estimate_in_house", "arguments": [5]},
    {"estimator": "get_order_status", "arguments": {"order_id": "ORD-062"}},
    {"estimator": "estimate_in_house", "arguments": {"pieces": 5}, "extra": 1},
])
def test_feasibility_rejects_bad_requests(setup, payload):
    client, _ = setup
    response = client.post("/feasibility/estimate", json=payload)
    assert response.status_code == 400 and response.json()["code"] == "INVALID_REQUEST"


def test_evidence_returns_one_csv_row(setup):
    client, _ = setup
    body = client.get("/evidence/orders.csv:110").json()
    assert body == {"id": "orders.csv:110", "source": "track1/data/orders.csv", "row": 110,
                    "data": csv_line("orders.csv", 110)}
    assert body["data"]["order_id"] == "ORD-062"


@pytest.mark.parametrize("evidence_id", [
    "orders.csv:1", "orders.csv:0", "orders.csv:99999", "orders.csv", "notes.csv:2",
    "..%2Fconfig.py:1", "orders.csv:-2", "orders.csv:２",
])
def test_evidence_refuses_anything_but_a_data_row(setup, evidence_id):
    client, _ = setup
    response = client.get(f"/evidence/{evidence_id}")
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
