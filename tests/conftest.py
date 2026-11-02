from datetime import datetime

import pytest

from app.desk import Desk
from app.extract import Enquiry
from app.kb import KnowledgeBase
from app.worktime import IST
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ist(y, m, d, h=10, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=IST)


@pytest.fixture
def kb():
    return KnowledgeBase.from_markdown(ROOT / "data" / "school_kb.md")


@pytest.fixture
def desk():
    return Desk(["Ananya", "Rahul"])


@pytest.fixture
def lead(desk):
    return desk.add_enquiry("Priya Rao", "9876543210", "website", "LKG admission", Enquiry(grade="LKG"), ist(2026, 11, 2, 10))
