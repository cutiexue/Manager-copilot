"""The demo backend (no API key) runs the real service, tools and actions with a keyword model."""

from demo_backend import build_service


def test_demo_model_drives_the_real_tools_and_proposals(tmp_path):
    service = build_service(tmp_path / "demo.db")
    session = service.create_session("Demo")["id"]

    lookup = service.send_message(session, "Where is ORD-062?")
    assert lookup["answer"].startswith("[demo model]")
    assert [c["name"] for c in lookup["tool_calls"]] == ["trace_order"]
    assert any(ref["id"] == "orders.csv:110" for ref in lookup["evidence"]["refs"])

    remind = service.send_message(session, "Remind me to chase ord 2 tomorrow")
    assert [p["status"] for p in remind["proposals"]] == ["PROPOSED"]
    assert service.actions.list_reminders() == []  # nothing is saved until the manager confirms
