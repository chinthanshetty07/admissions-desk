"""The admissions pipeline: leads, stage changes, counsellor assignment and follow-up discipline.

Stages run enquiry -> contacted -> visit scheduled -> visited -> applied -> enrolled, and a lead can be lost
from any open stage (with a reason). Every open lead always has a next follow-up time, so nothing silently
goes cold; the follow-up targets are in working time.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from .extract import Enquiry
from .worktime import IST, add_working_minutes, working_minutes_between

STAGES = ["enquiry", "contacted", "visit_scheduled", "visited", "applied", "enrolled"]
TERMINAL = {"enrolled", "lost"}
DAY = 9 * 60  # one working day in minutes

# How long each open stage may sit before a counsellor must act, in working minutes.
FOLLOW_UP_AFTER = {
    "enquiry": 60,              # first call within an hour of office time
    "contacted": 2 * DAY,       # get a visit booked
    "visited": 1 * DAY,         # share fees in writing, invite the application
    "applied": 3 * DAY,         # child interaction and offer
}
ALLOWED = {
    "enquiry": {"contacted", "visit_scheduled", "lost"},
    "contacted": {"contacted", "visit_scheduled", "lost"},
    "visit_scheduled": {"visit_scheduled", "visited", "lost"},
    "visited": {"visited", "applied", "lost"},
    "applied": {"applied", "enrolled", "lost"},
}
LOST_REASONS = {"fees", "distance", "chose_other_school", "no_response", "admission_not_needed", "other"}


class TransitionError(ValueError):
    pass


@dataclass
class Lead:
    id: int
    parent_name: str
    phone: str
    source: str
    message: str
    grade: str | None
    board: str | None
    area: str | None
    counsellor: str
    stage: str
    created_at: datetime
    first_response_at: datetime | None
    next_follow_up: datetime | None
    visit_at: datetime | None
    lost_reason: str | None

    @property
    def masked_phone(self) -> str:
        return ("*" * max(len(self.phone) - 4, 0)) + self.phone[-4:]


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY, parent_name TEXT NOT NULL, phone TEXT NOT NULL, source TEXT NOT NULL,
    message TEXT NOT NULL, grade TEXT, board TEXT, area TEXT, counsellor TEXT NOT NULL,
    stage TEXT NOT NULL, created_at TEXT NOT NULL, first_response_at TEXT, next_follow_up TEXT,
    visit_at TEXT, lost_reason TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL REFERENCES leads(id), type TEXT NOT NULL,
    at TEXT NOT NULL, note TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_open ON leads(stage, next_follow_up);
"""


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class Desk:
    def __init__(self, counsellors: list[str], db_path: str = ":memory:") -> None:
        if not counsellors:
            raise ValueError("At least one counsellor is needed")
        self.counsellors = counsellors
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # --- intake -----------------------------------------------------------------------------------
    def add_enquiry(self, parent_name: str, phone: str, source: str, message: str, enquiry: Enquiry,
                    at: datetime) -> Lead:
        at = at.astimezone(IST)
        counsellor = self._least_loaded()
        cur = self.db.execute(
            "INSERT INTO leads (parent_name, phone, source, message, grade, board, area, counsellor, stage, "
            "created_at, next_follow_up) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (parent_name, phone, source, message, enquiry.grade, enquiry.board, enquiry.area, counsellor,
             "enquiry", at.isoformat(), add_working_minutes(at, FOLLOW_UP_AFTER["enquiry"]).isoformat()))
        self._event(cur.lastrowid, "enquiry", at, f"via {source}")
        self.db.commit()
        return self.get(cur.lastrowid)

    def _least_loaded(self) -> str:
        load = {c: 0 for c in self.counsellors}
        for row in self.db.execute("SELECT counsellor, COUNT(*) n FROM leads WHERE stage NOT IN ('enrolled','lost') GROUP BY counsellor"):
            if row["counsellor"] in load:
                load[row["counsellor"]] = row["n"]
        return min(self.counsellors, key=lambda c: (load[c], self.counsellors.index(c)))

    # --- stage changes ----------------------------------------------------------------------------
    def record(self, lead_id: int, event: str, at: datetime, visit_at: datetime | None = None,
               reason: str | None = None, note: str | None = None) -> Lead:
        lead = self.get(lead_id)
        at = at.astimezone(IST)
        if lead.stage in TERMINAL:
            raise TransitionError(f"Lead {lead_id} is already {lead.stage}")
        if event not in ALLOWED[lead.stage]:
            raise TransitionError(f"Cannot go from {lead.stage} to {event}")
        if at < lead.created_at:
            raise TransitionError("Event is earlier than the enquiry")
        if event == "lost" and reason not in LOST_REASONS:
            raise TransitionError(f"A lost lead needs a reason: one of {sorted(LOST_REASONS)}")
        if event == "visit_scheduled" and (visit_at is None or visit_at.astimezone(IST) < at):
            raise TransitionError("A scheduled visit needs a future visit time")

        first_response = lead.first_response_at or at   # any counsellor action counts as the first response
        if event == "visit_scheduled":
            # Follow up the morning after the visit if nobody marks it as done.
            follow = add_working_minutes(visit_at.astimezone(IST) + timedelta(hours=2), 0)
        elif event in TERMINAL:
            follow = None
        else:
            follow = add_working_minutes(at, FOLLOW_UP_AFTER[event])
        self.db.execute(
            "UPDATE leads SET stage=?, first_response_at=?, next_follow_up=?, visit_at=COALESCE(?, visit_at), "
            "lost_reason=? WHERE id=?",
            (event, first_response.isoformat(), follow.isoformat() if follow else None,
             visit_at.astimezone(IST).isoformat() if visit_at else None, reason, lead_id))
        self._event(lead_id, event, at, note or reason)
        self.db.commit()
        return self.get(lead_id)

    def _event(self, lead_id: int, type_: str, at: datetime, note: str | None) -> None:
        self.db.execute("INSERT INTO events (lead_id, type, at, note) VALUES (?,?,?,?)", (lead_id, type_, at.isoformat(), note))

    # --- reads ------------------------------------------------------------------------------------
    def get(self, lead_id: int) -> Lead:
        row = self.db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if row is None:
            raise KeyError(lead_id)
        return self._lead(row)

    def leads(self) -> list[Lead]:
        return [self._lead(r) for r in self.db.execute("SELECT * FROM leads ORDER BY id")]

    def events(self, lead_id: int) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT type, at, note FROM events WHERE lead_id=? ORDER BY id", (lead_id,))]

    def follow_ups(self, now: datetime, counsellor: str | None = None) -> list[dict]:
        """Open leads whose follow-up is due, most overdue first."""
        now = now.astimezone(IST)
        out = []
        for lead in self.leads():
            if lead.stage in TERMINAL or lead.next_follow_up is None or lead.next_follow_up > now:
                continue
            if counsellor and lead.counsellor != counsellor:
                continue
            out.append({"lead_id": lead.id, "parent": lead.parent_name, "phone": lead.masked_phone,
                        "grade": lead.grade, "stage": lead.stage, "counsellor": lead.counsellor,
                        "due": lead.next_follow_up.isoformat(),
                        "overdue_working_minutes": working_minutes_between(lead.next_follow_up, now)})
        return sorted(out, key=lambda x: -x["overdue_working_minutes"])

    @staticmethod
    def _lead(r: sqlite3.Row) -> Lead:
        return Lead(r["id"], r["parent_name"], r["phone"], r["source"], r["message"], r["grade"], r["board"],
                    r["area"], r["counsellor"], r["stage"], _dt(r["created_at"]), _dt(r["first_response_at"]),
                    _dt(r["next_follow_up"]), _dt(r["visit_at"]), r["lost_reason"])
