"""Sanity checks on the read-only Track 1 CSVs (plan §6.5)."""

from datetime import date
from pathlib import Path

import data_loader
from data_loader import STAGES, load_orders, load_production, load_workshops

BACKEND = Path(data_loader.__file__).resolve().parent


def test_row_counts_match_the_course_dataset():
    assert len(load_orders()) == 120
    assert len(load_production()) == 360
    assert len(load_workshops()) == 8


def test_order_and_workshop_status_split():
    orders = load_orders()
    assert sum(o["status"] == "COMPLETE" for o in orders) == 86
    assert sum(o["status"] == "IN_PROGRESS" for o in orders) == 34
    assert sum(w["status"] == "ACTIVE" for w in load_workshops()) == 7


def test_production_log_covers_90_days_of_four_stages():
    records = load_production()
    days = sorted({r["date"] for r in records})
    assert (days[0], days[-1], len(days)) == ("2026-01-01", "2026-03-31", 90)
    assert {r["stage"] for r in records} == set(STAGES)


def test_sunday_output_is_zero():
    sundays = [r for r in load_production() if date.fromisoformat(r["date"]).weekday() == 6]
    assert len(sundays) == 52
    assert all(r["pieces_completed"] == "0" for r in sundays)


def test_source_labels_point_at_real_files():
    # 工具和前端证据抽屉引用的路径必须真实存在，否则溯源链接会断。
    for source in (data_loader.ORDERS_SOURCE, data_loader.PRODUCTION_SOURCE,
                   data_loader.WORKSHOPS_SOURCE):
        assert (BACKEND / source).is_file()
