"""The instant acknowledgement a parent gets. Built from templates and knowledge-base text only, so it can't
invent a fee, a seat or a deadline; anything the knowledge base doesn't cover goes to the counsellor."""
from __future__ import annotations

from dataclasses import dataclass, field

from .extract import Enquiry
from .kb import KnowledgeBase


@dataclass
class Reply:
    text: str
    answered: list[dict] = field(default_factory=list)     # {"question", "section"}
    for_counsellor: list[str] = field(default_factory=list)


def compose(parent_name: str, enquiry: Enquiry, counsellor: str, kb: KnowledgeBase, school: str) -> Reply:
    first = parent_name.split()[0] if parent_name.strip() else "there"
    grade = f" for {enquiry.grade}" if enquiry.grade else ""
    lines = [f"Hello {first}, thank you for your interest in {school}{grade}."]
    out = Reply(text="")
    seen = set()
    for q in enquiry.questions:
        ans = kb.search(q)
        if ans and ans.section not in seen:
            seen.add(ans.section)
            lines.append(f"{ans.section}: {ans.text}")
            out.answered.append({"question": q, "section": ans.section})
        elif not ans:
            out.for_counsellor.append(q)
    if out.for_counsellor:
        lines.append("Your counsellor will confirm the rest personally.")
    if enquiry.wants_visit:
        visits = kb.search("campus visit timings")
        lines.append(f"{counsellor} will call you to book a campus visit." + (f" {visits.text}" if visits and visits.section not in seen else ""))
    else:
        lines.append(f"{counsellor}, our admissions counsellor, will call you shortly.")
    out.text = "\n".join(lines)
    return out
