"""Turns a parent's free-text enquiry into a structured lead.

The model (when enabled) only extracts fields into a fixed schema; it never writes the reply to the parent.
Without an API key the rule-based extractor runs, so the whole app works offline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

GRADES = ["Nursery", "LKG", "UKG"] + [f"Grade {i}" for i in range(1, 13)]
BOARDS = ["CBSE", "ICSE", "IB", "IGCSE", "State"]
TOPICS = ["fees", "transport", "curriculum", "timings", "visit", "age", "documents", "daycare", "process"]


@dataclass
class Enquiry:
    grade: str | None = None
    board: str | None = None
    area: str | None = None
    wants_visit: bool = False
    questions: list[str] = field(default_factory=list)   # the parent's questions, verbatim-ish
    provider: str = "rules"


_GRADE_PATTERNS = [
    (re.compile(r"\b(nursery|pre-?nursery|playgroup)\b", re.I), lambda m: "Nursery"),
    (re.compile(r"\blkg\b", re.I), lambda m: "LKG"),
    (re.compile(r"\bukg\b", re.I), lambda m: "UKG"),
    (re.compile(r"\b(?:class|grade|std\.?|standard)\s*(1[0-2]|[1-9])(?:st|nd|rd|th)?\b", re.I), lambda m: f"Grade {int(m.group(1))}"),
    (re.compile(r"\b(1[0-2]|[1-9])(?:st|nd|rd|th)\s*(?:class|grade|std|standard)\b", re.I), lambda m: f"Grade {int(m.group(1))}"),
]
_BOARD = re.compile(r"\b(cbse|icse|ib|igcse|state board)\b", re.I)
_VISIT = re.compile(r"\b(visit|tour|see the (school|campus)|come (to|and see)|walk ?through)\b", re.I)
_AREAS = ["Marathahalli", "Whitefield", "Bellandur", "HSR Layout", "Sarjapur Road", "Kadubeesanahalli",
          "Indiranagar", "Koramangala", "Brookefield", "Mahadevapura", "KR Puram", "Electronic City"]


def _split_questions(text: str) -> list[str]:
    parts = re.split(r"(?<=[?.!])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip().endswith("?") or re.match(r"^(what|how|when|is|are|do|does|can|which)\b", p.strip(), re.I)]


class RuleExtractor:
    name = "rules"

    def extract(self, text: str) -> Enquiry:
        e = Enquiry()
        for pattern, fn in _GRADE_PATTERNS:
            m = pattern.search(text)
            if m:
                e.grade = fn(m)
                break
        m = _BOARD.search(text)
        if m:
            b = m.group(1).upper()
            e.board = "State" if b == "STATE BOARD" else b
        low = text.lower()
        e.area = next((a for a in _AREAS if a.lower() in low), None)
        e.wants_visit = bool(_VISIT.search(text))
        e.questions = _split_questions(text)
        return e


SYSTEM_PROMPT = (
    "You extract fields from a parent's school-admission enquiry for an Indian K-12 school.\n"
    "Return only what the message states; use null when a field is not mentioned. Do not infer a grade from age.\n"
    "questions: each distinct question the parent asks, short, in their words."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "grade": {"anyOf": [{"type": "string", "enum": GRADES}, {"type": "null"}]},
        "board": {"anyOf": [{"type": "string", "enum": BOARDS}, {"type": "null"}]},
        "area": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "wants_visit": {"type": "boolean"},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["grade", "board", "area", "wants_visit", "questions"],
    "additionalProperties": False,
}


class ClaudeExtractor:
    """Extraction with Claude structured outputs (EXTRACTOR=claude). Falls back to rules on any failure."""

    name = "claude"
    model = "claude-opus-5-5"

    def __init__(self, client=None, fallback: RuleExtractor | None = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self._fallback = fallback or RuleExtractor()

    def extract(self, text: str) -> Enquiry:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": f"<enquiry>\n{text}\n</enquiry>"}],
            )
        except Exception as exc:  # outage or rate limit: degrade, don't drop the enquiry
            return self._degraded(text, f"error:{type(exc).__name__}")
        if response.stop_reason == "refusal":
            return self._degraded(text, "refusal")
        raw = next((b.text for b in response.content if b.type == "text"), "")
        try:
            d = json.loads(raw)
            return Enquiry(d["grade"], d["board"], d["area"], bool(d["wants_visit"]), list(d["questions"]), self.name)
        except (json.JSONDecodeError, KeyError, TypeError):
            return self._degraded(text, "unparseable")

    def _degraded(self, text: str, why: str) -> Enquiry:
        e = self._fallback.extract(text)
        e.provider = f"rules (claude {why})"
        return e
