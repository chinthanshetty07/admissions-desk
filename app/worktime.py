"""Admissions-office working hours (IST): Monday to Saturday, 9 am to 6 pm.

Response targets are measured in working minutes, so an enquiry at 10 pm on Saturday is due Monday morning,
not "overdue" all of Sunday.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")
OPEN, CLOSE = time(9, 0), time(18, 0)


def is_open(t: datetime) -> bool:
    return t.weekday() < 6 and OPEN <= t.timetz().replace(tzinfo=None) < CLOSE


def next_open(t: datetime) -> datetime:
    t = t.astimezone(IST)
    while True:
        day_open = t.replace(hour=OPEN.hour, minute=0, second=0, microsecond=0)
        day_close = t.replace(hour=CLOSE.hour, minute=0, second=0, microsecond=0)
        if t.weekday() < 6:
            if t < day_open:
                return day_open
            if t < day_close:
                return t
        t = (t + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def add_working_minutes(start: datetime, minutes: int) -> datetime:
    t = next_open(start)
    while True:
        close = t.replace(hour=CLOSE.hour, minute=0, second=0, microsecond=0)
        left = (close - t).total_seconds() / 60
        if minutes <= left:
            return t + timedelta(minutes=minutes)
        minutes -= int(left)
        t = next_open(close)


def working_minutes_between(a: datetime, b: datetime) -> int:
    """Working minutes elapsed from a to b (0 if b <= a)."""
    total, t = 0, next_open(a)
    while t < b:
        close = t.replace(hour=CLOSE.hour, minute=0, second=0, microsecond=0)
        end = min(close, b)
        total += max(0, int((end - t).total_seconds() // 60))
        t = next_open(close)
    return total
