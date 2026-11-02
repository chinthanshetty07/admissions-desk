from app.extract import RuleExtractor
from app.reply import compose


def test_finds_the_right_section(kb):
    assert kb.search("Do you have a school bus from HSR?").section == "Transport"
    assert kb.search("what is the syllabus followed").section == "Curriculum and board"
    assert kb.search("which documents are required").section == "Documents"
    assert kb.search("how old should my child be for LKG").section == "Age criteria"


def test_unrelated_question_gets_no_answer(kb):
    assert kb.search("Do you have a swimming pool?") is None


def test_reply_never_states_a_fee_the_kb_does_not_have(kb):
    e = RuleExtractor().extract("Grade 3 admission. What are the fees? Is there a swimming pool?")
    r = compose("Priya Rao", e, "Ananya", kb, "Greenfield Public School")
    assert "shared by the admissions counsellor after the campus visit" in r.text
    assert r.for_counsellor == ["Is there a swimming pool?"]
    assert "confirm the rest personally" in r.text
    assert "Hello Priya" in r.text and "for Grade 3" in r.text


def test_visit_request_adds_visit_hours_once(kb):
    e = RuleExtractor().extract("LKG. Can we visit the campus?")
    r = compose("Rohit", e, "Rahul", kb, "Greenfield Public School")
    assert "Rahul will call you to book a campus visit" in r.text
    assert r.text.count("10 am to 1 pm") == 1
