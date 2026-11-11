"""Make the flat backend modules importable when pytest runs from any directory."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import rules  # noqa: E402


@pytest.fixture(autouse=True)
def course_data():
    """Every test starts on the course data (v0); a test that loads a snapshot cannot leak it."""
    rules.set_current_data("v0", rules.SNAPSHOT)
    yield
    rules.set_current_data("v0", rules.SNAPSHOT)
