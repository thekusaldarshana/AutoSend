"""Human-like sending rhythm: random gaps, random batch sizes, random breaks."""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta


@dataclass
class Pace:
    gap_min: float = 15.0        # seconds between messages
    gap_max: float = 45.0
    batch_min: int = 20          # messages before a break
    batch_max: int = 35
    break_min: float = 6.0       # minutes
    break_max: float = 15.0
    typing: bool = True          # show "typing…" before sending
    daily_cap: int = 0           # 0 = unlimited
    window_on: bool = False      # only send between these hours
    window_start: int = 9
    window_end: int = 19

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Pace":
        base = cls()
        for k, v in (d or {}).items():
            if hasattr(base, k):
                cur = getattr(base, k)
                try:
                    setattr(base, k, bool(v) if isinstance(cur, bool) else type(cur)(v))
                except (TypeError, ValueError):
                    pass
        return base


PRESETS: dict[str, dict] = {
    "careful": dict(gap_min=25.0, gap_max=70.0, batch_min=12, batch_max=20, break_min=10.0, break_max=25.0),
    "balanced": dict(gap_min=15.0, gap_max=45.0, batch_min=20, batch_max=35, break_min=6.0, break_max=15.0),
    "fast": dict(gap_min=8.0, gap_max=25.0, batch_min=30, batch_max=50, break_min=3.0, break_max=8.0),
}
PRESET_LABELS = {
    "careful": ("Careful", "Slowest and gentlest. Best for large lists."),
    "balanced": ("Balanced", "Recommended for everyday use."),
    "fast": ("Fast", "Quicker, with shorter breaks."),
}


def preset_name(p: Pace) -> str:
    for name, vals in PRESETS.items():
        if all(getattr(p, k) == v for k, v in vals.items()):
            return name
    return "custom"


class Scheduler:
    def __init__(self, pace: Pace, rng: random.Random | None = None):
        self.p = pace
        self.rng = rng or random.Random()
        self._in_batch = 0
        self._batch_target = self._new_target()

    def _new_target(self) -> int:
        lo, hi = sorted((max(1, int(self.p.batch_min)), max(1, int(self.p.batch_max))))
        return self.rng.randint(lo, hi)

    def gap(self) -> float:
        """Random pause after a message. Skewed short, with the odd longer one."""
        lo, hi = sorted((self.p.gap_min, self.p.gap_max))
        g = lo + (hi - lo) * self.rng.betavariate(1.6, 2.4)
        if self.rng.random() < 0.05:                      # occasionally get "distracted"
            g += self.rng.uniform(hi * 0.5, hi * 1.5)
        return g

    def pause_after_send(self) -> tuple[float, bool]:
        """(seconds to wait, is_break)."""
        self._in_batch += 1
        if self._in_batch >= self._batch_target:
            self._in_batch = 0
            self._batch_target = self._new_target()
            lo, hi = sorted((self.p.break_min, self.p.break_max))
            return self.rng.uniform(lo, hi) * 60.0, True
        return self.gap(), False

    def typing_seconds(self, text_len: int) -> float:
        if not self.p.typing:
            return 0.0
        base = min(9.0, text_len / 60.0)
        return max(1.5, min(12.0, base + self.rng.uniform(1.0, 3.0)))


def estimate_seconds(p: Pace, n: int) -> float:
    """Rough total time for n messages (ignores the sending-hours window)."""
    if n <= 0:
        return 0.0
    mean_gap = p.gap_min + (p.gap_max - p.gap_min) * (1.6 / 4.0) + 0.05 * p.gap_max
    typing = 4.0 if p.typing else 0.0
    per = mean_gap + typing + 1.0
    mean_batch = max(1.0, (p.batch_min + p.batch_max) / 2.0)
    breaks = max(0, int((n - 1) // mean_batch))
    return n * per + breaks * ((p.break_min + p.break_max) / 2.0) * 60.0


def in_window(p: Pace, now: datetime) -> bool:
    if not p.window_on:
        return True
    s, e = p.window_start, p.window_end
    if s == e:
        return True
    return s <= now.hour < e if s < e else (now.hour >= s or now.hour < e)


def seconds_until_window(p: Pace, now: datetime) -> float:
    if in_window(p, now):
        return 0.0
    start = now.replace(hour=p.window_start, minute=0, second=0, microsecond=0)
    if start <= now:
        start += timedelta(days=1)
    return (start - now).total_seconds()


def human_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} sec"
    m = seconds // 60
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min" if m else f"{h} h"
