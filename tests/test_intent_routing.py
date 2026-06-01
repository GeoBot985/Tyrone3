from tools.gobook_tools import detect_rpa_intent
from tools.workspace_tools import detect_workspace_intent


def test_detect_rpa_open_courts_phrase():
    assert detect_rpa_intent("What courts are open on 2026-06-05 between 17:00 and 18:00?") == "open_courts"


def test_detect_workspace_calendar_create_not_next():
    assert detect_workspace_intent("Add a calendar event for lunch tomorrow") == "calendar_create"


def test_detect_rpa_report_on_bookings_stays_none():
    assert detect_rpa_intent("I need a report on bookings") is None
