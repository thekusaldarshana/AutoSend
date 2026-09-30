"""Local database (SQLite): settings, message templates, variables, synced students, runs and history."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .excel import RosterRow
from .templating import Variable

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS templates(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '', updated_at REAL);
CREATE TABLE IF NOT EXISTS variables(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE, kind TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '', number_format TEXT NOT NULL DEFAULT 'none', prefix TEXT NOT NULL DEFAULT '',
    suffix TEXT NOT NULL DEFAULT '', transform TEXT NOT NULL DEFAULT 'none', fallback TEXT NOT NULL DEFAULT '',
    sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS students(
    key TEXT PRIMARY KEY, row_no INTEGER, data TEXT NOT NULL, phone TEXT, phone_error TEXT,
    wa_jid TEXT, wa_state TEXT, selected INTEGER NOT NULL DEFAULT 1, present INTEGER NOT NULL DEFAULT 1,
    first_seen REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS campaigns(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, body TEXT, image_path TEXT, created_at REAL,
    finished_at REAL, state TEXT NOT NULL DEFAULT 'running');
CREATE TABLE IF NOT EXISTS sends(
    id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL, student_key TEXT NOT NULL,
    name TEXT, phone TEXT, message TEXT, status TEXT NOT NULL DEFAULT 'pending', error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0, updated_at REAL, sent_at REAL, grp TEXT);
CREATE TABLE IF NOT EXISTS daily_counts(day TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_sends_campaign ON sends(campaign_id, status);
CREATE TABLE IF NOT EXISTS contacts(
    id INTEGER PRIMARY KEY AUTOINCREMENT, fields TEXT NOT NULL, wa_state TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS lists(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'static',
    rule TEXT NOT NULL DEFAULT '{}', template_id INTEGER, created_at REAL);
CREATE TABLE IF NOT EXISTS list_members(
    list_id INTEGER NOT NULL, ref TEXT NOT NULL, added_at REAL, PRIMARY KEY(list_id, ref));
"""


@dataclass
class SyncDiff:
    added: int = 0
    updated: int = 0
    removed: int = 0
    total: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)


class Database:
    def __init__(self, path: str | Path):
        self._lock = threading.RLock()
        self._c = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._c.row_factory = sqlite3.Row
        self._c.execute("PRAGMA journal_mode=WAL")
        self._c.execute("PRAGMA synchronous=NORMAL")
        self._c.executescript(SCHEMA)
        cols = {r["name"] for r in self._c.execute("PRAGMA table_info(sends)")}
        if "grp" not in cols:                                   # older databases
            self._c.execute("ALTER TABLE sends ADD COLUMN grp TEXT")

    # ------------------------------------------------------------ helpers
    def _q(self, sql: str, args=()):
        with self._lock:
            return self._c.execute(sql, args).fetchall()

    def _x(self, sql: str, args=()):
        with self._lock:
            return self._c.execute(sql, args)

    def close(self):
        with self._lock:
            self._c.close()

    # ----------------------------------------------------------- settings
    def get(self, key: str, default=None):
        rows = self._q("SELECT value FROM settings WHERE key=?", (key,))
        if not rows:
            return default
        try:
            return json.loads(rows[0]["value"])
        except (ValueError, TypeError):
            return default

    def set(self, key: str, value) -> None:
        self._x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)))

    # ---------------------------------------------------------- templates
    def list_templates(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM templates ORDER BY id")]

    def get_template(self, tid: int) -> dict | None:
        r = self._q("SELECT * FROM templates WHERE id=?", (tid,))
        return dict(r[0]) if r else None

    def save_template(self, tid: int | None, name: str, body: str, image_path: str = "") -> int:
        now = time.time()
        with self._lock:
            if tid is None:
                cur = self._c.execute("INSERT INTO templates(name,body,image_path,updated_at) VALUES(?,?,?,?)",
                                      (name, body, image_path, now))
                return int(cur.lastrowid)
            self._c.execute("UPDATE templates SET name=?, body=?, image_path=?, updated_at=? WHERE id=?",
                            (name, body, image_path, now, tid))
            return tid

    def delete_template(self, tid: int) -> None:
        self._x("DELETE FROM templates WHERE id=?", (tid,))

    # ---------------------------------------------------------- variables
    @staticmethod
    def _var(r: sqlite3.Row) -> Variable:
        return Variable(id=r["id"], name=r["name"], kind=r["kind"], source=r["source"],
                        number_format=r["number_format"], prefix=r["prefix"], suffix=r["suffix"],
                        transform=r["transform"], fallback=r["fallback"], sort=r["sort"])

    def list_variables(self) -> list[Variable]:
        return [self._var(r) for r in self._q("SELECT * FROM variables ORDER BY sort, id")]

    def save_variable(self, v: Variable) -> int:
        with self._lock:
            if v.id is None:
                nxt = self._c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM variables").fetchone()[0]
                cur = self._c.execute(
                    "INSERT INTO variables(name,kind,source,number_format,prefix,suffix,transform,fallback,sort)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (v.name, v.kind, v.source, v.number_format, v.prefix, v.suffix, v.transform, v.fallback, nxt))
                return int(cur.lastrowid)
            self._c.execute(
                "UPDATE variables SET name=?,kind=?,source=?,number_format=?,prefix=?,suffix=?,transform=?,fallback=?"
                " WHERE id=?",
                (v.name, v.kind, v.source, v.number_format, v.prefix, v.suffix, v.transform, v.fallback, v.id))
            return v.id

    def delete_variable(self, vid: int) -> None:
        self._x("DELETE FROM variables WHERE id=?", (vid,))

    # ----------------------------------------------------------- students
    def sync_students(self, rows: list[RosterRow]) -> SyncDiff:
        """Make the students table mirror the Excel file. Selection and WhatsApp checks are preserved."""
        now = time.time()
        diff = SyncDiff(total=len(rows))
        with self._lock:
            self._c.execute("BEGIN")
            try:
                existing = {r["key"]: r for r in self._c.execute("SELECT * FROM students")}
                seen = set()
                for r in rows:
                    seen.add(r.key)
                    data = json.dumps(r.values, ensure_ascii=False, sort_keys=True)
                    old = existing.get(r.key)
                    if old is None:
                        self._c.execute(
                            "INSERT INTO students(key,row_no,data,phone,phone_error,selected,present,first_seen,updated_at)"
                            " VALUES(?,?,?,?,?,1,1,?,?)", (r.key, r.row_no, data, r.phone, r.phone_error, now, now))
                        diff.added += 1
                        continue
                    phone_changed = (old["phone"] or "") != (r.phone or "")
                    if old["data"] != data or phone_changed or not old["present"]:
                        if old["data"] != data or phone_changed:
                            diff.updated += 1
                        self._c.execute(
                            "UPDATE students SET row_no=?, data=?, phone=?, phone_error=?, present=1, updated_at=?,"
                            " wa_jid=CASE WHEN ? THEN NULL ELSE wa_jid END,"
                            " wa_state=CASE WHEN ? THEN NULL ELSE wa_state END WHERE key=?",
                            (r.row_no, data, r.phone, r.phone_error, now, int(phone_changed), int(phone_changed), r.key))
                    elif old["row_no"] != r.row_no:
                        self._c.execute("UPDATE students SET row_no=? WHERE key=?", (r.row_no, r.key))
                for key, old in existing.items():
                    if key not in seen and old["present"]:
                        self._c.execute("UPDATE students SET present=0, updated_at=? WHERE key=?", (now, key))
                        diff.removed += 1
                self._c.execute("COMMIT")
            except Exception:
                self._c.execute("ROLLBACK")
                raise
        return diff

    @staticmethod
    def _student(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["values"] = json.loads(d.pop("data"))
        d["selected"] = bool(d["selected"])
        d["present"] = bool(d["present"])
        return d

    def list_students(self, present_only: bool = True) -> list[dict]:
        sql = "SELECT * FROM students" + (" WHERE present=1" if present_only else "") + " ORDER BY row_no"
        return [self._student(r) for r in self._q(sql)]

    def get_student(self, key: str) -> dict | None:
        r = self._q("SELECT * FROM students WHERE key=?", (key,))
        return self._student(r[0]) if r else None

    def set_selected(self, keys: list[str], selected: bool) -> None:
        with self._lock:
            self._c.execute("BEGIN")
            self._c.executemany("UPDATE students SET selected=? WHERE key=?", [(int(selected), k) for k in keys])
            self._c.execute("COMMIT")

    def set_all_selected(self, selected: bool) -> None:
        self._x("UPDATE students SET selected=? WHERE present=1", (int(selected),))

    def set_wa(self, ref: str, jid: str | None, state: str | None) -> None:
        if ref.startswith("c:"):
            self._x("UPDATE contacts SET wa_state=? WHERE id=?", (state, int(ref[2:])))
        else:
            self._x("UPDATE students SET wa_jid=?, wa_state=? WHERE key=?", (jid, state, ref))

    def rename_student_key(self, old: str, new: str) -> None:
        """Keep selection, history and list membership when a student's ID is edited."""
        if old == new:
            return
        with self._lock:
            self._c.execute("BEGIN")
            try:
                self._c.execute("UPDATE OR REPLACE students SET key=? WHERE key=?", (new, old))
                self._c.execute("UPDATE sends SET student_key=? WHERE student_key=?", (new, old))
                self._c.execute("UPDATE OR REPLACE list_members SET ref=? WHERE ref=?", (new, old))
                self._c.execute("COMMIT")
            except Exception:
                self._c.execute("ROLLBACK")
                raise

    def forget_students(self, keys: list[str]) -> None:
        """Remove deleted students from every list."""
        with self._lock:
            self._c.execute("BEGIN")
            self._c.executemany("DELETE FROM list_members WHERE ref=?", [(k,) for k in keys])
            self._c.execute("COMMIT")

    # ----------------------------------------------------------- contacts
    def list_contacts(self) -> list[dict]:
        out = []
        for r in self._q("SELECT * FROM contacts ORDER BY id"):
            d = dict(r)
            d["fields"] = json.loads(d["fields"])
            out.append(d)
        return out

    def get_contact(self, cid: int) -> dict | None:
        r = self._q("SELECT * FROM contacts WHERE id=?", (cid,))
        if not r:
            return None
        d = dict(r[0])
        d["fields"] = json.loads(d["fields"])
        return d

    def save_contact(self, cid: int | None, fields: dict[str, str]) -> int:
        data = json.dumps(fields, ensure_ascii=False)
        with self._lock:
            if cid is None:
                cur = self._c.execute("INSERT INTO contacts(fields, created_at) VALUES(?,?)", (data, time.time()))
                return int(cur.lastrowid)
            self._c.execute("UPDATE contacts SET fields=?, wa_state=NULL WHERE id=?", (data, cid))
            return cid

    def delete_contacts(self, ids: list[int]) -> None:
        with self._lock:
            self._c.execute("BEGIN")
            self._c.executemany("DELETE FROM contacts WHERE id=?", [(i,) for i in ids])
            self._c.executemany("DELETE FROM list_members WHERE ref=?", [(f"c:{i}",) for i in ids])
            self._c.execute("COMMIT")

    # -------------------------------------------------------------- lists
    @staticmethod
    def _list(r: sqlite3.Row) -> dict:
        d = dict(r)
        try:
            d["rule"] = json.loads(d["rule"] or "{}")
        except ValueError:
            d["rule"] = {}
        return d

    def list_lists(self) -> list[dict]:
        return [self._list(r) for r in self._q("SELECT * FROM lists ORDER BY name COLLATE NOCASE")]

    def get_list(self, lid: int) -> dict | None:
        r = self._q("SELECT * FROM lists WHERE id=?", (lid,))
        return self._list(r[0]) if r else None

    def save_list(self, lid: int | None, name: str, kind: str, rule: dict, template_id: int | None) -> int:
        rj = json.dumps(rule, ensure_ascii=False)
        with self._lock:
            if lid is None:
                cur = self._c.execute("INSERT INTO lists(name,kind,rule,template_id,created_at) VALUES(?,?,?,?,?)",
                                      (name, kind, rj, template_id, time.time()))
                return int(cur.lastrowid)
            self._c.execute("UPDATE lists SET name=?, kind=?, rule=?, template_id=? WHERE id=?",
                            (name, kind, rj, template_id, lid))
            return lid

    def delete_list(self, lid: int) -> None:
        with self._lock:
            self._c.execute("BEGIN")
            self._c.execute("DELETE FROM list_members WHERE list_id=?", (lid,))
            self._c.execute("DELETE FROM lists WHERE id=?", (lid,))
            self._c.execute("COMMIT")

    def member_refs(self, lid: int) -> list[str]:
        return [r["ref"] for r in self._q("SELECT ref FROM list_members WHERE list_id=? ORDER BY added_at, ref", (lid,))]

    def add_members(self, lid: int, refs: list[str]) -> int:
        now = time.time()
        with self._lock:
            before = self._c.execute("SELECT COUNT(*) FROM list_members WHERE list_id=?", (lid,)).fetchone()[0]
            self._c.execute("BEGIN")
            self._c.executemany("INSERT OR IGNORE INTO list_members(list_id,ref,added_at) VALUES(?,?,?)",
                                [(lid, r, now) for r in refs])
            self._c.execute("COMMIT")
            after = self._c.execute("SELECT COUNT(*) FROM list_members WHERE list_id=?", (lid,)).fetchone()[0]
        return after - before

    def remove_members(self, lid: int, refs: list[str]) -> None:
        with self._lock:
            self._c.execute("BEGIN")
            self._c.executemany("DELETE FROM list_members WHERE list_id=? AND ref=?", [(lid, r) for r in refs])
            self._c.execute("COMMIT")

    # ------------------------------------------------------ runs & sends
    def create_campaign(self, name: str, body: str, image_path: str, entries: list[tuple]) -> int:
        """entries: (ref, label, phone[, class]) for everyone who should get the message."""
        now = time.time()
        with self._lock:
            self._c.execute("BEGIN")
            try:
                cur = self._c.execute("INSERT INTO campaigns(name,body,image_path,created_at,state) VALUES(?,?,?,?, 'running')",
                                      (name, body, image_path, now))
                cid = int(cur.lastrowid)
                self._c.executemany(
                    "INSERT INTO sends(campaign_id,student_key,name,phone,status,updated_at,grp) VALUES(?,?,?,?, 'pending', ?, ?)",
                    [(cid, e[0], e[1], e[2], now, (e[3] if len(e) > 3 else "") or "") for e in entries])
                self._c.execute("COMMIT")
                return cid
            except Exception:
                self._c.execute("ROLLBACK")
                raise

    def set_send_label(self, send_id: int, name: str) -> None:
        self._x("UPDATE sends SET name=? WHERE id=?", (name, send_id))

    def open_campaign(self) -> dict | None:
        """The most recent run that still has people waiting."""
        rows = self._q(
            "SELECT c.* FROM campaigns c WHERE c.state IN ('running','paused') AND EXISTS"
            " (SELECT 1 FROM sends s WHERE s.campaign_id=c.id AND s.status='pending') ORDER BY c.id DESC LIMIT 1")
        return dict(rows[0]) if rows else None

    def latest_campaign(self) -> dict | None:
        rows = self._q("SELECT * FROM campaigns ORDER BY id DESC LIMIT 1")
        return dict(rows[0]) if rows else None

    def get_campaign(self, cid: int) -> dict | None:
        rows = self._q("SELECT * FROM campaigns WHERE id=?", (cid,))
        return dict(rows[0]) if rows else None

    def set_campaign_state(self, cid: int, state: str) -> None:
        fin = time.time() if state in ("finished", "stopped") else None
        self._x("UPDATE campaigns SET state=?, finished_at=COALESCE(?, finished_at) WHERE id=?", (state, fin, cid))

    def close_stale_campaigns(self, keep: int | None = None) -> None:
        self._x("UPDATE campaigns SET state='stopped', finished_at=? WHERE state IN ('running','paused') AND id<>?",
                (time.time(), keep or -1))

    def next_pending(self, cid: int) -> dict | None:
        rows = self._q("SELECT * FROM sends WHERE campaign_id=? AND status='pending' ORDER BY id LIMIT 1", (cid,))
        return dict(rows[0]) if rows else None

    def update_send(self, send_id: int, status: str, error: str | None = None,
                    message: str | None = None, phone: str | None = None, bump: bool = False) -> None:
        now = time.time()
        if status == "sent":
            self._x("INSERT INTO daily_counts(day,n) VALUES(?,1) ON CONFLICT(day) DO UPDATE SET n=n+1",
                    (time.strftime("%Y-%m-%d"),))
        self._x(
            "UPDATE sends SET status=?, error=?, message=COALESCE(?,message), phone=COALESCE(?,phone),"
            " attempts=attempts+?, updated_at=?, sent_at=CASE WHEN ?='sent' THEN ? ELSE sent_at END WHERE id=?",
            (status, error, message, phone, 1 if bump else 0, now, status, now, send_id))

    def counts(self, cid: int) -> dict[str, int]:
        out = {"pending": 0, "sent": 0, "failed": 0, "skipped": 0}
        for r in self._q("SELECT status, COUNT(*) n FROM sends WHERE campaign_id=? GROUP BY status", (cid,)):
            out[r["status"]] = r["n"]
        out["total"] = sum(out.values())
        return out

    def send_states(self, cid: int) -> dict[str, tuple[str, str | None]]:
        return {r["student_key"]: (r["status"], r["error"])
                for r in self._q("SELECT student_key, status, error FROM sends WHERE campaign_id=?", (cid,))}

    def list_campaigns(self) -> list[dict]:
        out = []
        for r in self._q("SELECT * FROM campaigns ORDER BY id DESC"):
            d = dict(r)
            d["counts"] = self.counts(d["id"])
            out.append(d)
        return out

    def list_sends(self, cid: int) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM sends WHERE campaign_id=? ORDER BY id", (cid,))]

    def sent_today(self) -> int:
        day = time.strftime("%Y-%m-%d")
        start = time.mktime(time.strptime(day, "%Y-%m-%d"))
        counted = self._q("SELECT n FROM daily_counts WHERE day=?", (day,))
        live = int(self._q("SELECT COUNT(*) n FROM sends WHERE status='sent' AND sent_at>=?", (start,))[0]["n"])
        return max(live, int(counted[0]["n"]) if counted else 0)

    def delete_campaigns(self, ids: list[int]) -> int:
        """Remove runs and their messages from History."""
        if not ids:
            return 0
        with self._lock:
            self._c.execute("BEGIN")
            self._c.executemany("DELETE FROM sends WHERE campaign_id=?", [(i,) for i in ids])
            cur = self._c.executemany("DELETE FROM campaigns WHERE id=?", [(i,) for i in ids])
            self._c.execute("COMMIT")
        return len(ids)

    def requeue(self, cid: int, statuses: tuple[str, ...] = ("failed",)) -> int:
        marks = ",".join("?" * len(statuses))
        cur = self._x(f"UPDATE sends SET status='pending', error=NULL WHERE campaign_id=? AND status IN ({marks})",
                      (cid, *statuses))
        return cur.rowcount
