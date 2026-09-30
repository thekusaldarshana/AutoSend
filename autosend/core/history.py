"""History helpers: time periods (today, this week, ...) and natural sorting of class names."""
from __future__ import annotations

import calendar
import re
import time
from datetime import date, datetime, timedelta

# (key, label) in the order shown in the History filter
PERIODS = [
    ("all", "All time"), ("today", "Today"), ("week", "This week"), ("month", "This month"),
    ("last_month", "Last month"), ("three_months", "Last 3 months"), ("year", "This year"),
]


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _ts(d: date) -> float:
    return time.mktime(datetime(d.year, d.month, d.day).timetuple())


def period_range(kind: str, now: datetime | None = None) -> tuple[float | None, float | None]:
    """(start, end) as epoch seconds; `end` is exclusive. None means open-ended.

    - this week starts on Monday
    - last month is the calendar month before this one (in February that is January; in January it is December)
    - last 3 months is a rolling window: from the same day three months ago until now
    """
    today = (now or datetime.now()).date()
    if kind == "today":
        return _ts(today), _ts(today + timedelta(days=1))
    if kind == "week":
        monday = today - timedelta(days=today.weekday())
        return _ts(monday), _ts(monday + timedelta(days=7))
    if kind == "month":
        first = today.replace(day=1)
        return _ts(first), _ts(_add_months(first, 1))
    if kind == "last_month":
        first = today.replace(day=1)
        return _ts(_add_months(first, -1)), _ts(first)
    if kind == "three_months":
        return _ts(_add_months(today, -3)), _ts(today + timedelta(days=1))
    if kind == "year":
        return _ts(date(today.year, 1, 1)), _ts(date(today.year + 1, 1, 1))
    return None, None


def in_period(ts: float | None, kind: str, now: datetime | None = None) -> bool:
    if kind == "all":
        return True
    if ts is None:
        return False
    start, end = period_range(kind, now)
    return (start is None or ts >= start) and (end is None or ts < end)


def natural_key(text: str) -> list:
    """'Grade 4 A' sorts before 'Grade 10 A'."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text or "")]
