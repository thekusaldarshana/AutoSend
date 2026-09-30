"""Everyone AutoSend can message: students (from Excel) and contacts (added in the app), and Lists of them."""
from __future__ import annotations

from dataclasses import dataclass, field

from .db import Database
from .phone import normalize_phone
from .templating import _parse_number

OPS = [("is", "is"), ("is_not", "is not"), ("contains", "contains"), ("not_contains", "does not contain"),
       ("starts", "starts with"), ("empty", "is empty"), ("not_empty", "is not empty"),
       ("gt", "is greater than"), ("lt", "is less than")]
NO_VALUE_OPS = {"empty", "not_empty"}
TYPE_FIELD = "Type"          # pseudo-field: Student / Contact


@dataclass
class Recipient:
    ref: str                     # student key, or "c:<id>" for contacts
    kind: str                    # student | contact
    label: str
    values: dict[str, str]
    phone: str | None
    phone_error: str | None
    present: bool = True
    wa_state: str | None = None
    selected: bool = True
    row_no: int = 0
    group: str = ""                # class / grade, for filtering history
    extra: dict = field(default_factory=dict)

    @property
    def sendable(self) -> bool:
        return bool(self.phone) and self.present

    @property
    def type_label(self) -> str:
        return "Student" if self.kind == "student" else "Contact"


def contact_recipient(c: dict, name_col: str | None, cc: str, class_col: str | None = None) -> Recipient:
    f = dict(c["fields"])
    name = (f.get("Name") or "").strip()
    phone, err = normalize_phone(f.get("Phone", ""), cc)
    values = dict(f)
    if name_col and not values.get(name_col):
        values[name_col] = name          # so {Name} works for contacts even if Excel calls it "Student Name"
    return Recipient(ref=f"c:{c['id']}", kind="contact", label=name or (f.get("Phone") or f"Contact {c['id']}"),
                     values=values, phone=phone, phone_error=err, wa_state=c.get("wa_state"), row_no=10 ** 9 + c["id"],
                     group=(values.get(class_col, "") if class_col else "").strip())


def student_recipient(s: dict, name_col: str | None, class_col: str | None = None) -> Recipient:
    label = (s["values"].get(name_col) if name_col else "") or s["key"]
    return Recipient(ref=s["key"], kind="student", label=label, values=s["values"], phone=s["phone"],
                     phone_error=s.get("phone_error"), present=s["present"], wa_state=s.get("wa_state"),
                     selected=s["selected"], row_no=s["row_no"],
                     group=(s["values"].get(class_col, "") if class_col else "").strip())


def all_recipients(db: Database, name_col: str | None, cc: str, class_col: str | None = None) -> list[Recipient]:
    out = [student_recipient(s, name_col, class_col) for s in db.list_students()]
    out += [contact_recipient(c, name_col, cc, class_col) for c in db.list_contacts()]
    return out


def get_recipient(db: Database, ref: str, name_col: str | None, cc: str) -> Recipient | None:
    if ref.startswith("c:"):
        try:
            c = db.get_contact(int(ref[2:]))
        except ValueError:
            return None
        return contact_recipient(c, name_col, cc) if c else None
    s = db.get_student(ref)
    return student_recipient(s, name_col) if s else None


# ---------------------------------------------------------------- smart rules
def cond_matches(cond: dict, values: dict[str, str]) -> bool:
    op = cond.get("op", "is")
    v = (values.get(cond.get("field", "")) or "").strip()
    t = (cond.get("value") or "").strip()
    vl, tl = v.lower(), t.lower()
    if op == "is":
        return vl == tl
    if op == "is_not":
        return vl != tl
    if op == "contains":
        return tl in vl
    if op == "not_contains":
        return tl not in vl
    if op == "starts":
        return vl.startswith(tl)
    if op == "empty":
        return v == ""
    if op == "not_empty":
        return v != ""
    if op in ("gt", "lt"):
        a, b = _parse_number(v), _parse_number(t)
        if a is None or b is None:
            return False
        return a > b if op == "gt" else a < b
    return False


def rule_matches(rule: dict, r: Recipient) -> bool:
    conds = rule.get("conds") or []
    if not conds:
        return False
    vals = dict(r.values)
    vals[TYPE_FIELD] = r.type_label
    hits = (cond_matches(c, vals) for c in conds)
    return any(hits) if rule.get("match") == "any" else all(hits)


def describe_rule(rule: dict) -> str:
    conds = rule.get("conds") or []
    if not conds:
        return "No rule yet"
    labels = dict(OPS)
    parts = []
    for c in conds:
        p = f"{c.get('field')} {labels.get(c.get('op'), c.get('op'))}"
        if c.get("op") not in NO_VALUE_OPS:
            p += f" “{c.get('value', '')}”"
        parts.append(p)
    return (" or " if rule.get("match") == "any" else " and ").join(parts)


def list_members(db: Database, lst: dict, everyone: list[Recipient]) -> list[Recipient]:
    if lst["kind"] == "smart":
        return [r for r in everyone if r.present and rule_matches(lst["rule"], r)]
    refs = set(db.member_refs(lst["id"]))
    return [r for r in everyone if r.present and r.ref in refs]


def available_fields(db: Database, columns: list[str]) -> list[str]:
    fields = [TYPE_FIELD] + list(columns)
    for c in db.list_contacts():
        for k in c["fields"]:
            if k not in fields:
                fields.append(k)
    return fields
