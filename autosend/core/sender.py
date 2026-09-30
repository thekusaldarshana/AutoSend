"""The sending loop: one message at a time, human-paced, resumable, never double-sends."""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from . import antiban
from .db import Database
from .recipients import get_recipient
from .templating import render
from .whatsapp import NotOnWhatsApp, SendError

log = logging.getLogger("autosend.sender")

CAPTION_LIMIT = 1000        # longer texts go out as photo + separate text

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def keep_awake(on: bool) -> None:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except Exception:
        pass


class SendController(QObject):
    stateChanged = Signal(str, str)        # running | paused | waiting | finished | stopped, message
    itemDone = Signal(str, str, str)       # student_key, status, detail
    progress = Signal(int, dict)           # campaign_id, counts
    countdown = Signal(str, int)           # label, seconds left
    activity = Signal(str)                 # human sentence for the live log

    def __init__(self, db: Database, wa, pace_fn, name_col_fn, cc_fn=lambda: "94", parent=None):
        super().__init__(parent)
        self.db, self.wa = db, wa
        self._pace_fn, self._name_col_fn, self._cc_fn = pace_fn, name_col_fn, cc_fn
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self.campaign_id: int | None = None
        self.state = "idle"
        self._jid_cache: dict[str, object] = {}

    # -------------------------------------------------------------- control
    @property
    def active(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, campaign_id: int) -> None:
        if self.active:
            return
        self.campaign_id = campaign_id
        self._stop.clear()
        self._pause.clear()
        self._thread = threading.Thread(target=self._run, args=(campaign_id,), name="sender", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self._pause.set()
        self._emit_state("paused", "Paused. Nothing is being sent.")

    def resume(self) -> None:
        self._pause.clear()
        self._emit_state("running", "")

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()

    def join(self, timeout: float = 3.0) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _emit_state(self, state: str, msg: str) -> None:
        self.state = state
        self.stateChanged.emit(state, msg)

    # -------------------------------------------------------------- helpers
    def _sleep(self, seconds: float, label: str) -> bool:
        """Interruptible sleep with a live countdown. False if stopped."""
        end = time.time() + seconds
        last = -1
        while True:
            if self._stop.is_set():
                return False
            if self._pause.is_set():
                held = time.time()
                while self._pause.is_set() and not self._stop.is_set():
                    time.sleep(0.2)
                end += time.time() - held
                continue
            left = end - time.time()
            if left <= 0:
                return True
            if int(left) != last:
                last = int(left)
                self.countdown.emit(label, last + 1)
            time.sleep(min(0.25, left))

    def _wait_for_wa(self, timeout: float = 180.0) -> bool:
        if self.wa.ready:
            return True
        self.activity.emit("WhatsApp disconnected. Waiting for it to come back…")
        self._emit_state("waiting", "Waiting for WhatsApp to reconnect…")
        end = time.time() + timeout
        while time.time() < end and not self._stop.is_set():
            if self.wa.ready:
                self._emit_state("running", "")
                return True
            time.sleep(1)
        return self.wa.ready

    def _mark(self, send: dict, status: str, detail: str = "", message: str | None = None,
              phone: str | None = None, bump: bool = False) -> None:
        self.db.update_send(send["id"], status, detail or None, message, phone, bump)
        self.itemDone.emit(send["student_key"], status, detail)
        self.progress.emit(send["campaign_id"], self.db.counts(send["campaign_id"]))

    # ----------------------------------------------------------------- loop
    def _run(self, cid: int) -> None:
        keep_awake(True)
        camp = self.db.get_campaign(cid)
        if not camp:
            return
        pace = antiban.Pace.from_dict(self._pace_fn())
        sched = antiban.Scheduler(pace)
        self.db.set_campaign_state(cid, "running")
        self._emit_state("running", "")
        self.progress.emit(cid, self.db.counts(cid))
        consecutive_fail = 0
        try:
            while not self._stop.is_set():
                send = self.db.next_pending(cid)
                if send is None:
                    self.db.set_campaign_state(cid, "finished")
                    self._emit_state("finished", "All done.")
                    return

                # sending hours
                now = datetime.now()
                if not antiban.in_window(pace, now):
                    wait = antiban.seconds_until_window(pace, now)
                    self._emit_state("waiting", f"Waiting for sending hours ({pace.window_start}:00).")
                    self.activity.emit(f"Outside sending hours. Will continue at {pace.window_start}:00.")
                    if not self._sleep(wait, "Sending hours begin in"):
                        break
                    self._emit_state("running", "")
                    continue
                if pace.daily_cap and self.db.sent_today() >= pace.daily_cap:
                    self.db.set_campaign_state(cid, "paused")
                    self._emit_state("stopped", f"Daily limit of {pace.daily_cap} messages reached. Resume tomorrow.")
                    self.activity.emit("Daily limit reached. You can resume tomorrow.")
                    return
                if not self._wait_for_wa():
                    self.db.set_campaign_state(cid, "paused")
                    self._emit_state("stopped", "WhatsApp is not connected. Reconnect it and press Resume.")
                    return

                outcome = self._send_one(send, camp, sched)
                if outcome == "sent":
                    consecutive_fail = 0
                    if self.db.next_pending(cid) is None:
                        continue
                    wait, is_break = sched.pause_after_send()
                    if is_break:
                        self.activity.emit(f"Taking a short break ({antiban.human_duration(wait)}).")
                        self._emit_state("waiting", "Taking a short break to keep things natural.")
                        ok = self._sleep(wait, "Break ends in")
                        self._emit_state("running", "")
                    else:
                        ok = self._sleep(wait, "Next message in")
                    if not ok:
                        break
                elif outcome == "failed":
                    consecutive_fail += 1
                    if consecutive_fail >= 4:
                        self.db.set_campaign_state(cid, "paused")
                        self._emit_state("stopped", "Several messages failed in a row. Check your internet and WhatsApp, then Resume.")
                        self.activity.emit("Stopped: several messages failed in a row.")
                        return
                    if not self._sleep(8, "Retrying in"):
                        break
                # skipped -> straight to the next person
            # stopped by user
            self.db.set_campaign_state(cid, "paused")
            self._emit_state("stopped", "Stopped. You can resume later.")
        except Exception:
            log.exception("sender crashed")
            self.db.set_campaign_state(cid, "paused")
            self._emit_state("stopped", "Something went wrong. Your progress is saved; press Resume to continue.")
        finally:
            keep_awake(False)
            self.progress.emit(cid, self.db.counts(cid))

    def _send_one(self, send: dict, camp: dict, sched: antiban.Scheduler) -> str:
        key = send["student_key"]
        label = send.get("name") or key
        person = get_recipient(self.db, key, self._name_col_fn(), self._cc_fn())
        if person is None or not person.present:
            self._mark(send, "skipped", "No longer in your list")
            self.activity.emit(f"Skipped {label}: no longer in your list.")
            return "skipped"
        label = person.label or label
        phone = person.phone
        if not phone:
            self._mark(send, "skipped", person.phone_error or "No phone number")
            self.activity.emit(f"Skipped {label}: {person.phone_error or 'no phone number'}.")
            return "skipped"

        res = render(camp["body"], self.db.list_variables(), person.values)
        if res.unknown:
            self._mark(send, "skipped", "Unknown variable: " + ", ".join("{" + u + "}" for u in res.unknown))
            return "skipped"
        if res.missing:
            self._mark(send, "skipped", "Empty: " + ", ".join(res.missing))
            self.activity.emit(f"Skipped {label}: {', '.join(res.missing)} is empty.")
            return "skipped"
        if not res.text:
            self._mark(send, "skipped", "Message is empty")
            return "skipped"

        try:
            jid = self._jid_cache.get(phone)
            if jid is None:
                jid = self.wa.resolve(phone)
                self._jid_cache[phone] = jid
                self.db.set_wa(key, None, "yes")
        except NotOnWhatsApp:
            self.db.set_wa(key, None, "no")
            self._mark(send, "failed", "Not on WhatsApp", res.text, phone, bump=True)
            self.activity.emit(f"{label}: this number is not on WhatsApp.")
            return "skipped"       # not a connection problem, so don't count toward the failure streak
        except SendError as e:
            self._mark(send, "failed", str(e), res.text, phone, bump=True)
            return "failed"

        image = camp.get("image_path") or ""
        for attempt in (1, 2):
            try:
                self.wa.typing(jid, sched.typing_seconds(len(res.text)), self._stop.is_set)
                if self._stop.is_set():
                    return "skipped"
                if image and len(res.text) <= CAPTION_LIMIT:
                    self.wa.send_image(jid, image, res.text)
                elif image:
                    self.wa.send_image(jid, image, None)
                    time.sleep(2.0)
                    self.wa.send_text(jid, res.text)
                else:
                    self.wa.send_text(jid, res.text)
                self._mark(send, "sent", "", res.text, phone, bump=True)
                self.activity.emit(f"Sent to {label}.")
                return "sent"
            except SendError as e:
                log.warning("send to %s failed (attempt %s): %s", phone, attempt, e)
                if attempt == 1 and not self._stop.is_set():
                    if not self._wait_for_wa(60) or not self._sleep(10, "Retrying in"):
                        break
                    continue
                self._mark(send, "failed", str(e)[:200], res.text, phone, bump=True)
                self.activity.emit(f"Could not send to {label}.")
                return "failed"
        return "skipped"
