"""The demo backend (no API key) runs the real service, tools and actions with a keyword model."""

from demo_backend import build_service


def test_demo_model_drives_the_real_tools_and_proposals(tmp_path):
    service = build_service(tmp_path / "demo.db")
    session = service.create_session("Demo")["id"]

    lookup = service.send_message(session, "Where is ORD-062?")
    assert lookup["answer"].startswith("[demo model]")
    assert [c["name"] for c in lookup["tool_calls"]] == ["trace_order"]
    assert any(ref["id"] == "orders.csv:110@v0" and ref["data_version"] == "v0"
               for ref in lookup["evidence"]["refs"])

    remind = service.send_message(session, "Remind me to chase ord 2 tomorrow")
    assert [p["status"] for p in remind["proposals"]] == ["PROPOSED"]
    assert service.actions.list_reminders() == []  # nothing is saved until the manager confirms


def test_demo_dates_follow_the_selected_snapshot(tmp_path):
    service = build_service(tmp_path / "demo.db")
    service.actions.set_data_version("v2")
    session = service.create_session("Later snapshot")["id"]

    for question in ("Which orders are at risk?", "Show a morning briefing"):
        reply = service.send_message(session, question)
        tool = reply["tool_calls"][0]
        assert tool["arguments"]["as_of_date"] == "2026-04-03"
        assert tool["result"]["status"] == "ok"
        assert tool["result"]["as_of_date"] == "2026-04-03"

    watch = service.send_message(session, "Watch ORD-002")
    assert watch["tool_calls"][0]["arguments"]["deadline"] == "2026-04-04"
    assert watch["proposals"][0]["status"] == "PROPOSED"
