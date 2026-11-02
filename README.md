# Admissions Desk

[![CI](https://github.com/chinthanshetty07/admissions-desk/actions/workflows/ci.yml/badge.svg)](https://github.com/chinthanshetty07/admissions-desk/actions/workflows/ci.yml)

**Live dashboard (synthetic data): https://chinthanshetty07.github.io/admissions-desk/**

An AI-assisted admissions desk for a K-12 school. It turns a parent's free-text enquiry into a structured lead,
answers their questions instantly from the school's own information, assigns a counsellor, and then makes sure
nobody goes cold between enquiry, campus visit, application and enrolment. Leadership gets a dashboard that shows
**where families drop out and why**, not just how many enquiries came in.

Built as an independent prototype after reading EduFlourish's description of the admissions problem: enquiries
get slow replies, follow-ups vary from counsellor to counsellor, and leadership sees the enquiry count rather than
the movement from enquiry to visit to application to enrolment. It is not affiliated with EduFlourish; the school
("Greenfield Public School") and every family in it are fictional.

## What happens to an enquiry

```
parent message -> extract fields (rules | Claude) -> lead + counsellor -> instant reply from the school's KB
               -> follow-up timer per stage -> dashboard + overdue list
```

1. **Extraction.** "Hi, we stay in Whitefield. LKG for my daughter. Is it CBSE? What are the fees? Can we visit
   on Saturday?" becomes grade `LKG`, board `CBSE`, area `Whitefield`, wants a visit, and three questions.
   The default extractor is rule-based and works offline. With `EXTRACTOR=claude` it uses Claude structured
   outputs into a fixed schema; any API error, refusal or malformed output falls back to the rules, so an
   outage never drops an enquiry.
2. **Instant reply, without inventing anything.** Each question is matched (BM25) against the school's own
   knowledge base (`data/school_kb.md`) and answered with that section's text. The model never writes the reply,
   so it cannot quote a fee, promise a seat or make up a deadline. Questions the knowledge base doesn't cover
   ("Is there a swimming pool?") are passed to the counsellor instead of guessed.
3. **Assignment.** The counsellor with the fewest open leads gets it.
4. **Follow-up discipline.** Every open lead always has a next follow-up time, measured in office hours
   (Mon–Sat, 9 am–6 pm IST), so a Saturday-night enquiry is due Monday morning rather than "overdue" all Sunday:

   | Stage | Counsellor must act within |
   |---|---|
   | Enquiry | 1 working hour (first call) |
   | Contacted | 2 working days (book a visit) |
   | Visit scheduled | the morning after the visit, if it isn't marked done |
   | Visited | 1 working day (fees in writing, invite the application) |
   | Applied | 3 working days (interaction and offer) |

5. **Stage rules.** Stages can only move forward along the funnel; a lost lead needs a reason (fees, distance,
   chose another school, no response…); a closed lead can't be changed. Every change is an event, so the
   history is auditable.

## The dashboard

Funnel with step-by-step conversion, why families were lost, median first-call time and the share called within
an hour, each counsellor's speed, open and overdue leads, conversion by source, and the overdue follow-up list
(phone numbers masked). The live demo is two simulated months of 240 enquiries; one counsellor is deliberately
slow to call back, which shows up in the first-call column.

## Run it

```bash
pip install -r requirements-dev.txt
pytest -q                          # 32 tests
python -m scripts.seed             # simulate two months, write the dashboard's data
uvicorn app.main:app --reload      # API + dashboard on http://localhost:8000
```

```bash
curl -X POST localhost:8000/enquiries -H 'content-type: application/json' -d '{
  "parent_name": "Kavya Iyer", "phone": "9876500011", "source": "instagram",
  "message": "UKG admission. Do you have transport from Bellandur? Can we visit?"}'
curl -X POST localhost:8000/leads/1/events -H 'content-type: application/json' -d '{"type": "contacted"}'
curl localhost:8000/api/follow-ups
curl localhost:8000/api/report
```

Set `EXTRACTOR=claude` and `ANTHROPIC_API_KEY` in your environment to use Claude for extraction. No key is
stored in the code or the repository.

## Tests

| Area | Covered |
|---|---|
| Office hours | late-Saturday enquiry due Monday, rolling over closing time, overdue time excluding nights and Sundays |
| Extraction | grades in many phrasings (class 3, 10th std, UKG, pre-nursery), board, area, visit intent, question splitting, no grade guessed from age; Claude path and its three fallbacks |
| Knowledge base | right section for paraphrased questions, no answer for unrelated ones, fees never invented, visit hours added once |
| Pipeline | first-call target, least-loaded assignment, full journey and follow-up times, invalid transitions, closed leads, overdue list with masked phones, funnel and first-response maths |
| API | enquiry to enrolment over HTTP, 404/409/422 errors, dashboard served |

## Not done (and what I'd do next)

- WhatsApp and website-form intake (the API is the seam for both), and reminders sent to parents.
- Multi-school tenancy and counsellor logins; this has none, so it should not be exposed publicly as is.
- The knowledge base is a markdown file; a school would edit it in a small admin screen. With hundreds of
  sections, embeddings would beat BM25; at this size BM25 is easier to debug.
- Grade-specific counsellor routing, holidays in the office calendar, and seat availability per grade.

Built with Claude Code; the tests and the simulated dashboard are how I checked what it wrote.
