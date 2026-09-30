"""Message variables and rendering.

A message is plain text with {Placeholders}. Each placeholder is a *variable* the
user can create/edit/delete: a spreadsheet column, a fixed text, or today's date.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

VAR_RE = re.compile(r"\{([^{}\n]{1,40})\}")

KINDS = ("column", "text", "today")
NUMBER_FORMATS = ("none", "thousands")
TRANSFORMS = ("none", "upper", "lower", "title")


@dataclass
class Variable:
    name: str
    kind: str = "column"           # column | text | today
    source: str = ""               # column header | fixed text | date format
    number_format: str = "none"    # none | thousands
    prefix: str = ""
    suffix: str = ""
    transform: str = "none"
    fallback: str = ""             # used when the value is empty
    id: int | None = None
    sort: int = 0


@dataclass
class RenderResult:
    text: str
    missing: list[str] = field(default_factory=list)   # variables with empty values
    unknown: list[str] = field(default_factory=list)   # {names} that are not defined

    @property
    def ok(self) -> bool:
        return not self.missing and not self.unknown


_DATE_TOKENS = [("yyyy", "%Y"), ("MMMM", "%B"), ("MMM", "%b"), ("MM", "%m"), ("dd", "%d"), ("yy", "%y")]


def format_date(d: date, fmt: str) -> str:
    out = fmt or "dd/MM/yyyy"
    slots = {}
    for i, (tok, code) in enumerate(_DATE_TOKENS):
        key = f"\x00{i}\x00"
        if tok in out:
            out = out.replace(tok, key)
            slots[key] = code
    for key, code in slots.items():
        out = out.replace(key, d.strftime(code))
    return out


def _parse_number(s: str) -> Decimal | None:
    t = s.strip().replace(",", "").replace(" ", "")
    if not t:
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _apply_number_format(value: str, fmt: str) -> str:
    if fmt != "thousands":
        return value
    n = _parse_number(value)
    if n is None or not n.is_finite():
        return value
    if n == n.to_integral_value():
        return f"{int(n):,}"
    return f"{n:,.2f}"


def _apply_transform(value: str, t: str) -> str:
    if t == "upper":
        return value.upper()
    if t == "lower":
        return value.lower()
    if t == "title":
        return value.title()
    return value


def resolve(var: Variable, row: dict[str, str], today: date | None = None) -> str:
    """Final text for one variable and one student ('' if empty and no fallback)."""
    if var.kind == "today":
        return format_date(today or date.today(), var.source)
    if var.kind == "text":
        raw = var.source
    else:
        raw = (row.get(var.source) or "").strip()
    if not raw:
        return var.fallback
    value = _apply_transform(_apply_number_format(raw, var.number_format), var.transform)
    return f"{var.prefix}{value}{var.suffix}"


def used_names(body: str) -> list[str]:
    seen, out = set(), []
    for m in VAR_RE.finditer(body):
        n = m.group(1).strip()
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def render(body: str, variables: list[Variable], row: dict[str, str], today: date | None = None) -> RenderResult:
    by_name = {v.name.lower(): v for v in variables}
    missing: list[str] = []
    unknown: list[str] = []

    def sub(m: re.Match) -> str:
        name = m.group(1).strip()
        var = by_name.get(name.lower())
        if var is None:
            if name not in unknown:
                unknown.append(name)
            return m.group(0)
        val = resolve(var, row, today)
        if val == "" and var.name not in missing:
            missing.append(var.name)
        return val

    text = VAR_RE.sub(sub, body).strip()
    return RenderResult(text=text, missing=missing, unknown=unknown)


def rename_in_body(body: str, old: str, new: str) -> str:
    def sub(m: re.Match) -> str:
        return "{" + new + "}" if m.group(1).strip().lower() == old.lower() else m.group(0)
    return VAR_RE.sub(sub, body)


_SAFE = re.compile(r"[^\w]", re.UNICODE)


def valid_variable_name(name: str) -> bool:
    return bool(name) and len(name) <= 40 and not re.search(r"[{}\n]", name) and name == name.strip()


def suggest_variables(columns: list[str], phone_col: str | None) -> list[Variable]:
    """Sensible starter variables for a spreadsheet's columns."""
    rules = [
        ("Admission", ("admission", "adm no", "adm.")),
        ("Name", ("name",)),
        ("Class", ("class", "grade")),
        ("Amount", ("amount", "outstanding", "balance", "due", "total", "fees")),
    ]
    out: list[Variable] = []
    taken: set[str] = set()
    for col in columns:
        if col == phone_col:
            continue
        low = col.lower()
        name = None
        for cand, hints in rules:
            if cand.lower() in taken:
                continue
            if any(h in low for h in hints):
                name = cand
                break
        if name is None:
            base = re.sub(r"\(.*?\)", "", col)
            words = [w for w in _SAFE.sub(" ", base).split() if w]
            name = "".join(w[:1].upper() + w[1:] for w in words) or "Column"
            n, i = name, 2
            while n.lower() in taken:
                n, i = f"{name}{i}", i + 1
            name = n
        taken.add(name.lower())
        v = Variable(name=name, kind="column", source=col)
        if name == "Amount":
            v.number_format = "thousands"
        out.append(v)
    out.append(Variable(name="Today", kind="today", source="dd/MM/yyyy"))
    return out
