"""What leadership needs to see: not the enquiry count, but where families drop out and why."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import median

from .desk import STAGES, TERMINAL, Desk
from .worktime import working_minutes_between


def _reached(lead, stage: str, history: set[str]) -> bool:
    if lead.stage == "lost":
        return stage in history
    return STAGES.index(lead.stage) >= STAGES.index(stage)


def report(desk: Desk, now: datetime) -> dict:
    leads = desk.leads()
    histories = {l.id: {e["type"] for e in desk.events(l.id)} | {"enquiry"} for l in leads}
    # A lead that was contacted and then booked a visit has "reached" contacted even if the event was skipped.
    for l in leads:
        h = histories[l.id]
        top = max((STAGES.index(s) for s in h if s in STAGES), default=0)
        h.update(STAGES[: top + 1])

    counts = {s: sum(1 for l in leads if _reached(l, s, histories[l.id])) for s in STAGES}
    steps = []
    for a, b in zip(STAGES, STAGES[1:]):
        steps.append({"from": a, "to": b, "rate": round(counts[b] / counts[a], 3) if counts[a] else None})

    first = [working_minutes_between(l.created_at, l.first_response_at) for l in leads if l.first_response_at]
    by_source: dict[str, Counter] = defaultdict(Counter)
    by_counsellor: dict[str, Counter] = defaultdict(Counter)
    for l in leads:
        by_source[l.source]["enquiries"] += 1
        by_source[l.source]["enrolled"] += l.stage == "enrolled"
        c = by_counsellor[l.counsellor]
        c["open"] += l.stage not in TERMINAL
        c["enrolled"] += l.stage == "enrolled"
        c["overdue"] += bool(l.stage not in TERMINAL and l.next_follow_up and l.next_follow_up <= now)
    calls: dict[str, list[int]] = defaultdict(list)
    for l in leads:
        if l.first_response_at:
            calls[l.counsellor].append(working_minutes_between(l.created_at, l.first_response_at))
    for name, mins in calls.items():
        by_counsellor[name]["median_first_call_minutes"] = median(mins)
    return {
        "as_of": now.isoformat(),
        "funnel": counts,
        "step_conversion": steps,
        "lost_reasons": dict(Counter(l.lost_reason for l in leads if l.stage == "lost").most_common()),
        "first_response_working_minutes": {
            "median": median(first) if first else None,
            "within_target_pct": round(100 * sum(m <= 60 for m in first) / len(first), 1) if first else None,
            "never_contacted": sum(1 for l in leads if l.first_response_at is None and l.stage not in TERMINAL),
        },
        "by_source": {s: {**c, "conversion": round(c["enrolled"] / c["enquiries"], 3)} for s, c in sorted(by_source.items())},
        "by_counsellor": {k: dict(v) for k, v in sorted(by_counsellor.items())},
        "overdue_follow_ups": len(desk.follow_ups(now)),
    }
