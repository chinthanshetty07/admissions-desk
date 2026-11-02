from fastapi.testclient import TestClient

from app import main
from app.desk import Desk


def client():
    main.app.state.desk = Desk(["Ananya", "Rahul"])
    return TestClient(main.app)


def test_enquiry_to_enrolment_over_http():
    c = client()
    r = c.post("/enquiries", json={"parent_name": "Kavya Iyer", "phone": "9876500011", "source": "instagram",
                                   "message": "UKG admission. Do you have transport from Bellandur? Can we visit?",
                                   "at": "2026-11-02T10:00:00+05:30"})
    assert r.status_code == 201
    body = r.json()
    lead_id = body["lead"]["id"]
    assert body["lead"]["grade"] == "UKG" and body["lead"]["phone"] == "******0011"
    assert {"question": "Do you have transport from Bellandur?", "section": "Transport"} in body["answered_from_kb"]
    assert "book a campus visit" in body["reply"]

    for ev in [{"type": "contacted", "at": "2026-11-02T10:15:00+05:30"},
               {"type": "visit_scheduled", "at": "2026-11-02T10:20:00+05:30", "visit_at": "2026-11-03T11:00:00+05:30"},
               {"type": "visited", "at": "2026-11-03T11:45:00+05:30"},
               {"type": "applied", "at": "2026-11-04T12:00:00+05:30"},
               {"type": "enrolled", "at": "2026-11-09T12:00:00+05:30"}]:
        assert c.post(f"/leads/{lead_id}/events", json=ev).status_code == 200
    rep = c.get("/api/report", params={"now": "2026-11-10T10:00:00+05:30"}).json()
    assert rep["funnel"]["enrolled"] == 1


def test_errors():
    c = client()
    assert c.post("/leads/99/events", json={"type": "contacted"}).status_code == 404
    bad_phone = {"parent_name": "X", "phone": "12", "source": "website", "message": "hi"}
    assert c.post("/enquiries", json=bad_phone).status_code == 422
    lead = c.post("/enquiries", json={**bad_phone, "phone": "9876500012"}).json()["lead"]
    r = c.post(f"/leads/{lead['id']}/events", json={"type": "enrolled"})
    assert r.status_code == 409


def test_dashboard_served():
    assert "Admissions Desk" in client().get("/").text
