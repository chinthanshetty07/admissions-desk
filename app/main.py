"""HTTP API and the dashboard. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .desk import Desk, TransitionError
from .extract import ClaudeExtractor, RuleExtractor
from .funnel import report
from .kb import KnowledgeBase
from .reply import compose
from .worktime import IST

ROOT = Path(__file__).resolve().parent.parent
SCHOOL = os.getenv("SCHOOL_NAME", "Greenfield Public School")
COUNSELLORS = [c.strip() for c in os.getenv("COUNSELLORS", "Ananya,Rahul,Meera").split(",") if c.strip()]


def build_extractor():
    return ClaudeExtractor() if os.getenv("EXTRACTOR", "rules") == "claude" else RuleExtractor()


app = FastAPI(title="Admissions Desk")
app.state.desk = Desk(COUNSELLORS, os.getenv("DB_PATH", ":memory:"))
app.state.kb = KnowledgeBase.from_markdown(ROOT / "data" / "school_kb.md")
app.state.extractor = build_extractor()


class EnquiryIn(BaseModel):
    parent_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(pattern=r"^\+?[0-9]{10,13}$")
    source: Literal["website", "walk_in", "phone", "referral", "instagram", "google", "whatsapp"]
    message: str = Field(min_length=1, max_length=2000)
    at: datetime | None = None   # for seeding demo data; defaults to now


class EventIn(BaseModel):
    type: Literal["contacted", "visit_scheduled", "visited", "applied", "enrolled", "lost"]
    at: datetime | None = None
    visit_at: datetime | None = None
    reason: str | None = None
    note: str | None = Field(default=None, max_length=500)


def _now(at: datetime | None) -> datetime:
    return (at or datetime.now(IST)).astimezone(IST)


def _lead_out(lead) -> dict:
    return {"id": lead.id, "parent": lead.parent_name, "phone": lead.masked_phone, "source": lead.source,
            "grade": lead.grade, "board": lead.board, "area": lead.area, "counsellor": lead.counsellor,
            "stage": lead.stage, "next_follow_up": lead.next_follow_up.isoformat() if lead.next_follow_up else None,
            "lost_reason": lead.lost_reason}


@app.post("/enquiries", status_code=201)
def new_enquiry(body: EnquiryIn):
    enquiry = app.state.extractor.extract(body.message)
    lead = app.state.desk.add_enquiry(body.parent_name, body.phone, body.source, body.message, enquiry, _now(body.at))
    reply = compose(body.parent_name, enquiry, lead.counsellor, app.state.kb, SCHOOL)
    return {"lead": _lead_out(lead), "extracted_by": enquiry.provider, "reply": reply.text,
            "answered_from_kb": reply.answered, "for_counsellor": reply.for_counsellor}


@app.post("/leads/{lead_id}/events")
def add_event(lead_id: int, body: EventIn):
    try:
        lead = app.state.desk.record(lead_id, body.type, _now(body.at), body.visit_at, body.reason, body.note)
    except KeyError:
        raise HTTPException(404, "No such lead")
    except TransitionError as e:
        raise HTTPException(409, str(e))
    return _lead_out(lead)


@app.get("/leads/{lead_id}")
def get_lead(lead_id: int):
    try:
        lead = app.state.desk.get(lead_id)
    except KeyError:
        raise HTTPException(404, "No such lead")
    return {**_lead_out(lead), "events": app.state.desk.events(lead_id)}


@app.get("/api/follow-ups")
def follow_ups(counsellor: str | None = None, now: datetime | None = None):
    return app.state.desk.follow_ups(_now(now), counsellor)


@app.get("/api/report")
def funnel_report(now: datetime | None = None):
    return report(app.state.desk, _now(now))


@app.get("/")
def dashboard():
    return FileResponse(ROOT / "web" / "index.html")
