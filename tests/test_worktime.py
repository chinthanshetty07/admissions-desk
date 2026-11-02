from app.worktime import add_working_minutes, working_minutes_between
from conftest import ist


def test_within_office_hours():
    assert add_working_minutes(ist(2026, 11, 2, 10), 60) == ist(2026, 11, 2, 11)


def test_late_saturday_enquiry_is_due_monday_morning():
    # Sat 7 Nov 2026, 10 pm -> Sunday is closed -> Monday 9 am + 60 min
    assert add_working_minutes(ist(2026, 11, 7, 22), 60) == ist(2026, 11, 9, 10)


def test_rolls_over_closing_time():
    assert add_working_minutes(ist(2026, 11, 2, 17, 30), 60) == ist(2026, 11, 3, 9, 30)


def test_working_minutes_between_skips_nights_and_sunday():
    assert working_minutes_between(ist(2026, 11, 7, 17), ist(2026, 11, 9, 10)) == 120
