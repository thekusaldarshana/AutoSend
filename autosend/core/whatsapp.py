"""WhatsApp connection (neonize / whatsmeow). No browser, no clicks.

neonize's connect() blocks, so it runs on its own thread. Everything the UI needs
comes out as Qt signals.
"""
from __future__ import annotations

import io
import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

log = logging.getLogger("autosend.wa")

# states
IDLE, STARTING, NEED_QR, CONNECTED, RECONNECTING, LOGGED_OUT, ERROR = (
    "idle", "starting", "need_qr", "connected", "reconnecting", "logged_out", "error")


class SendError(Exception):
    pass


class NotOnWhatsApp(SendError):
    pass


def qr_png(data: bytes | str, scale: int = 8) -> bytes:
    import segno
    if isinstance(data, bytes):
        data = data.decode("utf-8", "ignore")
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=scale, border=2, dark="#111B21")
    return buf.getvalue()


class WhatsAppService(QObject):
    stateChanged = Signal(str, str)     # state, detail (phone number or message)
    qrReady = Signal(bytes)             # PNG image bytes

    def __init__(self, session_db: Path, parent=None):
        super().__init__(parent)
        self._db = Path(session_db)
        self._client = None
        self._thread: threading.Thread | None = None
        self.state = IDLE
        self.detail = ""
        self.my_number = ""
        self.last_qr = b""
        self._want_stop = False
        self._lock = threading.RLock()

    # ------------------------------------------------------------ lifecycle
    def _set(self, state: str, detail: str = "") -> None:
        self.state, self.detail = state, detail
        log.info("state -> %s %s", state, detail)
        self.stateChanged.emit(state, detail)

    @property
    def ready(self) -> bool:
        return self.state == CONNECTED

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._want_stop = False
            self._set(STARTING)
            self._thread = threading.Thread(target=self._run, name="whatsapp", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        try:
            from neonize.client import NewClient
            from neonize.events import (ConnectedEv, ConnectFailureEv, DisconnectedEv, LoggedOutEv, PairStatusEv,
                                        TemporaryBanEv, ClientOutdatedEv)

            client = NewClient(str(self._db), uuid="autosend")
            self._client = client

            @client.qr
            def _on_qr(_c, data: bytes):
                try:
                    self.last_qr = qr_png(data)
                    self.qrReady.emit(self.last_qr)
                    if self.state != NEED_QR:
                        self._set(NEED_QR)
                except Exception:
                    log.exception("QR render failed")

            @client.event(ConnectedEv)
            def _on_connected(c, _ev):
                self.my_number = self._own_number(c)
                self.last_qr = b""
                self._set(CONNECTED, self.my_number)

            @client.event(PairStatusEv)
            def _on_pair(c, ev):
                log.info("paired: %s", getattr(ev, "ID", None))

            @client.event(DisconnectedEv)
            def _on_disc(_c, _ev):
                if not self._want_stop and self.state == CONNECTED:
                    self._set(RECONNECTING)

            @client.event(LoggedOutEv)
            def _on_logout(_c, _ev):
                self._set(LOGGED_OUT)

            @client.event(ConnectFailureEv)
            def _on_fail(_c, ev):
                log.warning("connect failure: %s %s", getattr(ev, "Reason", ""), getattr(ev, "Message", ""))

            @client.event(TemporaryBanEv)
            def _on_ban(_c, ev):
                self._set(ERROR, "WhatsApp has temporarily restricted this number. Wait before sending again.")

            @client.event(ClientOutdatedEv)
            def _on_old(_c, _ev):
                self._set(ERROR, "This version of AutoSend is too old for WhatsApp. Please update the app.")

            client.connect()          # blocks until stop()
        except Exception as e:  # pragma: no cover - depends on network/native lib
            log.exception("WhatsApp thread crashed")
            if not self._want_stop:
                self._set(ERROR, f"Could not start WhatsApp ({e.__class__.__name__}).")
        finally:
            self._client = None
            if not self._want_stop and self.state not in (LOGGED_OUT, ERROR):
                self._set(IDLE)

    @staticmethod
    def _own_number(client) -> str:
        try:
            me = client.get_me()
            return me.JID.User or ""
        except Exception:
            try:
                return client.me.JID.User or ""
            except Exception:
                return ""

    def stop(self) -> None:
        self._want_stop = True
        c = self._client
        if c is not None:
            try:
                c.stop()
            except Exception:
                log.exception("stop failed")
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=4)

    def relink(self) -> None:
        """Forget the current link and show a fresh QR code."""
        self.stop()
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                Path(str(self._db) + suffix).unlink()
            except FileNotFoundError:
                pass
            except OSError:
                log.exception("could not remove %s", suffix)
        self.my_number = ""
        self.start()

    def logout(self) -> None:
        c = self._client
        try:
            if c is not None and self.state == CONNECTED:
                c.logout()
        except Exception:
            log.exception("logout failed")
        self.relink()

    # -------------------------------------------------------------- sending
    def _need(self):
        c = self._client
        if c is None or self.state != CONNECTED:
            raise SendError("WhatsApp is not connected.")
        return c

    def resolve(self, phone_digits: str):
        """JID for a phone number. Raises NotOnWhatsApp if the number has no WhatsApp."""
        from neonize.utils.jid import build_jid
        c = self._need()
        try:
            res = c.is_on_whatsapp("+" + phone_digits)
        except Exception as e:
            log.warning("is_on_whatsapp failed for %s: %s", phone_digits, e)
            return build_jid(phone_digits)      # let the send itself decide
        if not res:
            return build_jid(phone_digits)
        r = res[0]
        if not r.IsIn:
            raise NotOnWhatsApp("This number is not on WhatsApp")
        return r.JID if r.JID.User else build_jid(phone_digits)

    def own_jid(self):
        from neonize.utils.jid import build_jid
        if not self.my_number:
            raise SendError("Your own number is not known yet.")
        return build_jid(self.my_number)

    def typing(self, jid, seconds: float, stop_flag=lambda: False) -> None:
        """Show 'typing…' for a while. Never fatal."""
        if seconds <= 0:
            return
        try:
            from neonize.utils.enum import ChatPresence, ChatPresenceMedia
            c = self._need()
            c.send_chat_presence(jid, ChatPresence.CHAT_PRESENCE_COMPOSING, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
            end = time.time() + seconds
            while time.time() < end and not stop_flag():
                time.sleep(0.2)
            c.send_chat_presence(jid, ChatPresence.CHAT_PRESENCE_PAUSED, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
        except Exception:
            log.debug("typing indicator failed", exc_info=True)

    def send_text(self, jid, text: str) -> str:
        c = self._need()
        try:
            resp = c.send_message(jid, text)
        except Exception as e:
            raise SendError(str(e) or e.__class__.__name__) from e
        return getattr(resp, "ID", "") or ""

    def send_image(self, jid, path: str, caption: str | None) -> str:
        c = self._need()
        try:
            resp = c.send_image(jid, str(path), caption=caption)
        except Exception as e:
            raise SendError(str(e) or e.__class__.__name__) from e
        return getattr(resp, "ID", "") or ""
