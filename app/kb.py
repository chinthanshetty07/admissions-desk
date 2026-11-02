"""Answers parent questions from the school's own knowledge base, with the section it came from.

Retrieval is BM25 over the knowledge-base sections: small, explainable and good enough for a few dozen
sections. If nothing scores well enough, the assistant says a counsellor will confirm instead of guessing.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an the is are am do does to of for in on at and or my our we i you your what which when how can "
            "there any with be it this that will from as by about please tell me us".split())
# Parents rarely use the knowledge base's words; map common phrasings onto them.
_SYNONYMS = {
    "bus": "transport", "buses": "transport", "van": "transport", "pickup": "transport",
    "fee": "fees", "cost": "fees", "charges": "fees", "price": "fees", "expensive": "fees",
    "syllabus": "curriculum", "cbse": "cbse", "board": "board",
    "timing": "timings", "time": "timings", "hours": "timings",
    "visit": "visits", "tour": "visits", "see": "visits",
    "age": "age", "old": "age", "eligible": "age", "eligibility": "age",
    "papers": "documents", "certificate": "documents", "documents": "documents",
    "daycare": "day", "creche": "day", "food": "meals", "lunch": "lunch",
}


def tokens(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        if w in _STOP:
            continue
        out.append(_SYNONYMS.get(w, w))
    return out


@dataclass(frozen=True)
class Section:
    title: str
    text: str


@dataclass(frozen=True)
class Answer:
    section: str
    text: str
    score: float


class KnowledgeBase:
    def __init__(self, sections: list[Section], min_score: float = 1.5) -> None:
        self.sections = sections
        self.min_score = min_score
        self._docs = [tokens(s.title + " " + s.title + " " + s.text) for s in sections]
        self._avg = sum(map(len, self._docs)) / max(len(self._docs), 1)
        df = Counter(t for d in self._docs for t in set(d))
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    @classmethod
    def from_markdown(cls, path: str | Path) -> "KnowledgeBase":
        sections, title, buf = [], None, []
        for line in Path(path).read_text().splitlines():
            if line.startswith("## "):
                if title:
                    sections.append(Section(title, " ".join(buf).strip()))
                title, buf = line[3:].strip(), []
            elif title and line.strip():
                buf.append(line.strip())
        if title:
            sections.append(Section(title, " ".join(buf).strip()))
        return cls(sections)

    def search(self, question: str, k1: float = 1.4, b: float = 0.75) -> Answer | None:
        q = tokens(question)
        best: Answer | None = None
        for sec, doc in zip(self.sections, self._docs):
            tf = Counter(doc)
            score = 0.0
            for t in set(q):
                if t not in tf:
                    continue
                f = tf[t]
                score += self._idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * len(doc) / self._avg))
            if best is None or score > best.score:
                best = Answer(sec.title, sec.text, round(score, 3))
        return best if best and best.score >= self.min_score else None
