import json
from types import SimpleNamespace

import pytest

from app.extract import ClaudeExtractor, RuleExtractor

rules = RuleExtractor()


@pytest.mark.parametrize("text,grade", [
    ("Admission for my son in class 3 please", "Grade 3"),
    ("looking for 10th std seat", "Grade 10"),
    ("Is there a seat in UKG?", "UKG"),
    ("pre-nursery admission?", "Nursery"),
    ("Grade 11 science", "Grade 11"),
])
def test_grade(text, grade):
    assert rules.extract(text).grade == grade


def test_fields_and_questions():
    e = rules.extract("Hi, we stay in Whitefield. LKG for my daughter. Is it CBSE? What are the fees? Can we visit on Saturday?")
    assert (e.grade, e.board, e.area, e.wants_visit) == ("LKG", "CBSE", "Whitefield", True)
    assert e.questions == ["Is it CBSE?", "What are the fees?", "Can we visit on Saturday?"]


def test_no_grade_is_not_guessed():
    assert rules.extract("My child is 5 years old, admission details?").grade is None


class FakeClient:
    def __init__(self, response=None, error=None):
        self.messages = SimpleNamespace(create=self._create)
        self._response, self._error = response, error

    def _create(self, **kwargs):
        if self._error:
            raise self._error
        return self._response


def _resp(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def test_claude_extraction_used_when_valid():
    body = {"grade": "Grade 4", "board": "ICSE", "area": None, "wants_visit": False, "questions": ["Fees?"]}
    e = ClaudeExtractor(client=FakeClient(_resp(json.dumps(body)))).extract("class four icse")
    assert (e.grade, e.board, e.provider) == ("Grade 4", "ICSE", "claude")


@pytest.mark.parametrize("client,why", [
    (FakeClient(error=TimeoutError()), "error:TimeoutError"),
    (FakeClient(_resp("", stop="refusal")), "refusal"),
    (FakeClient(_resp("not json")), "unparseable"),
])
def test_claude_failures_fall_back_to_rules(client, why):
    e = ClaudeExtractor(client=client).extract("UKG admission in Bellandur")
    assert e.grade == "UKG" and e.area == "Bellandur"
    assert e.provider == f"rules (claude {why})"
