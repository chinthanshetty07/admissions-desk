"""Simulates two months of a school's admissions desk with synthetic families and writes the dashboard's
static data (web/report.json, web/follow-ups.json) so the dashboard also works on GitHub Pages.

Everything here is made up: names, phone numbers and behaviour. Run: python -m scripts.seed
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from app.desk import Desk
from app.extract import RuleExtractor
from app.funnel import report
from app.worktime import IST, add_working_minutes

ROOT = Path(__file__).resolve().parent.parent
FIRST = ["Priya", "Rohit", "Sneha", "Arjun", "Kavya", "Vikram", "Divya", "Karthik", "Neha", "Suresh", "Asha", "Manoj"]
LAST = ["Rao", "Sharma", "Iyer", "Reddy", "Nair", "Gowda", "Menon", "Kulkarni", "Shetty", "Das"]
MESSAGES = [
    "Hi, looking for admission in {g} for my daughter. Do you have school bus from {a}? What are the fees?",
    "Want to know about {g} admission for 2027. Is it CBSE? Can we visit the campus this Saturday?",
    "My son is in {g} in another school. What documents are needed for transfer? Is there day care?",
    "Admission enquiry for {g}. What are the school timings?",
    "Please share details for {g}. We stay in {a}. How is the admission process?",
]
GRADES = ["Nursery", "LKG", "UKG", "class 1", "class 3", "grade 5", "class 7", "grade 9"]
AREAS = ["Marathahalli", "Whitefield", "Bellandur", "HSR Layout", "Sarjapur Road", "Koramangala"]
SOURCES = [("website", 0.3), ("google", 0.2), ("instagram", 0.15), ("referral", 0.15), ("walk_in", 0.1), ("whatsapp", 0.1)]
LOST = ["fees", "distance", "chose_other_school", "no_response", "other"]


def simulate(seed: int = 7, start=datetime(2026, 9, 1, tzinfo=IST), days: int = 61) -> tuple[Desk, datetime]:
    rnd = random.Random(seed)
    desk = Desk(["Ananya", "Rahul", "Meera"])
    ex = RuleExtractor()
    end = start + timedelta(days=days)
    # Rahul is stretched thin: slower first calls, so the dashboard has something to show.
    speed = {"Ananya": 40, "Rahul": 300, "Meera": 90}
    for _ in range(240):
        at = start + timedelta(minutes=rnd.randrange(days * 24 * 60))
        at = at.replace(hour=rnd.choice([8, 10, 11, 13, 16, 19, 21]), minute=rnd.randrange(60))
        src = rnd.choices([s for s, _ in SOURCES], [w for _, w in SOURCES])[0]
        msg = rnd.choice(MESSAGES).format(g=rnd.choice(GRADES), a=rnd.choice(AREAS))
        name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        lead = desk.add_enquiry(name, f"9{rnd.randrange(10**8, 10**9)}", src, msg, ex.extract(msg), at)

        t = add_working_minutes(at, int(rnd.expovariate(1 / speed[lead.counsellor])) + 5)
        if t > end or rnd.random() < 0.06:
            continue                                      # never called back
        if rnd.random() < (0.45 if speed[lead.counsellor] > 200 else 0.25):
            desk.record(lead.id, "lost", t, reason=rnd.choice(["no_response", "chose_other_school"]))
            continue
        desk.record(lead.id, "contacted", t)
        t2 = add_working_minutes(t, rnd.randrange(60, 3 * 540))
        if t2 > end:
            continue
        if rnd.random() < 0.3:
            desk.record(lead.id, "lost", t2, reason=rnd.choice(LOST))
            continue
        visit = add_working_minutes(t2, rnd.randrange(540, 4 * 540))
        desk.record(lead.id, "visit_scheduled", t2, visit_at=visit)
        if visit > end:
            continue
        if rnd.random() < 0.15:
            desk.record(lead.id, "lost", visit + timedelta(hours=1), reason="no_response")
            continue
        desk.record(lead.id, "visited", visit)
        t3 = add_working_minutes(visit, rnd.randrange(60, 5 * 540))
        if t3 > end:
            continue
        if rnd.random() < 0.35:
            desk.record(lead.id, "lost", t3, reason=rnd.choice(["fees", "distance", "chose_other_school"]))
            continue
        desk.record(lead.id, "applied", t3)
        t4 = add_working_minutes(t3, rnd.randrange(540, 6 * 540))
        if t4 > end:
            continue
        if rnd.random() < 0.7:
            desk.record(lead.id, "enrolled", t4)
        else:
            desk.record(lead.id, "lost", t4, reason="fees")
    return desk, end


def main() -> None:
    desk, now = simulate()
    rep = report(desk, now)
    (ROOT / "web" / "report.json").write_text(json.dumps(rep, indent=2, default=str))
    (ROOT / "web" / "follow-ups.json").write_text(json.dumps(desk.follow_ups(now)[:15], indent=2))
    print(json.dumps({k: rep[k] for k in ("funnel", "first_response_working_minutes", "overdue_follow_ups")}, indent=2))


if __name__ == "__main__":
    main()
