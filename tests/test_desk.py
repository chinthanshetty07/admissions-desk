import pytest

from app.desk import TransitionError
from app.extract import Enquiry
from app.funnel import report
from conftest import ist


def test_new_lead_gets_first_call_target(lead):
    assert lead.stage == "enquiry"
    assert lead.next_follow_up == ist(2026, 11, 2, 11)


def test_assigns_to_least_loaded_counsellor(desk):
    a = desk.add_enquiry("A", "9000000001", "website", "x", Enquiry(), ist(2026, 11, 2))
    b = desk.add_enquiry("B", "9000000002", "website", "x", Enquiry(), ist(2026, 11, 2))
    desk.record(a.id, "lost", ist(2026, 11, 2, 11), reason="distance")
    c = desk.add_enquiry("C", "9000000003", "website", "x", Enquiry(), ist(2026, 11, 2))
    assert (a.counsellor, b.counsellor, c.counsellor) == ("Ananya", "Rahul", "Ananya")


def test_happy_path_and_follow_ups(desk, lead):
    desk.record(lead.id, "contacted", ist(2026, 11, 2, 10, 20))
    l = desk.record(lead.id, "visit_scheduled", ist(2026, 11, 2, 10, 25), visit_at=ist(2026, 11, 4, 11))
    assert l.next_follow_up == ist(2026, 11, 4, 13)
    desk.record(lead.id, "visited", ist(2026, 11, 4, 11, 45))
    desk.record(lead.id, "applied", ist(2026, 11, 5, 12))
    l = desk.record(lead.id, "enrolled", ist(2026, 11, 10, 12))
    assert l.stage == "enrolled" and l.next_follow_up is None
    assert [e["type"] for e in desk.events(lead.id)] == ["enquiry", "contacted", "visit_scheduled", "visited", "applied", "enrolled"]


@pytest.mark.parametrize("event,kwargs,msg", [
    ("applied", {}, "Cannot go from enquiry to applied"),
    ("lost", {}, "needs a reason"),
    ("lost", {"reason": "bored"}, "needs a reason"),
    ("visit_scheduled", {}, "future visit time"),
])
def test_invalid_transitions(desk, lead, event, kwargs, msg):
    with pytest.raises(TransitionError, match=msg):
        desk.record(lead.id, event, ist(2026, 11, 2, 11), **kwargs)


def test_closed_lead_cannot_change(desk, lead):
    desk.record(lead.id, "lost", ist(2026, 11, 2, 11), reason="fees")
    with pytest.raises(TransitionError, match="already lost"):
        desk.record(lead.id, "contacted", ist(2026, 11, 2, 12))


def test_follow_up_list_shows_overdue_in_working_time_and_masks_phone(desk, lead):
    due = desk.follow_ups(ist(2026, 11, 3, 10))       # target was 2 Nov 11:00
    assert due[0]["overdue_working_minutes"] == 7 * 60 + 60
    assert due[0]["phone"] == "******3210"
    assert desk.follow_ups(ist(2026, 11, 2, 10, 30)) == []


def test_funnel_counts_and_first_response(desk, lead):
    other = desk.add_enquiry("B", "9000000002", "google", "x", Enquiry(), ist(2026, 11, 2, 10))
    desk.record(lead.id, "contacted", ist(2026, 11, 2, 10, 30))
    desk.record(lead.id, "visit_scheduled", ist(2026, 11, 2, 10, 35), visit_at=ist(2026, 11, 3, 11))
    desk.record(other.id, "visit_scheduled", ist(2026, 11, 2, 14), visit_at=ist(2026, 11, 4, 11))
    desk.record(other.id, "lost", ist(2026, 11, 4, 13), reason="distance")
    r = report(desk, ist(2026, 11, 5, 10))
    assert r["funnel"]["enquiry"] == 2
    assert r["funnel"]["contacted"] == 2          # booking a visit on the first call implies contact
    assert r["funnel"]["visit_scheduled"] == 2
    assert r["funnel"]["visited"] == 0
    assert r["lost_reasons"] == {"distance": 1}
    assert r["first_response_working_minutes"]["median"] == 135   # median of 30 and 240 minutes
    assert r["by_source"]["google"]["conversion"] == 0
