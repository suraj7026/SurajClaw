"""IMAP poller — turn email into agent turns.

Celery beat fires :func:`email_poll` every few minutes. For each UNSEEN
message we:

1. Decode subject + plain body.
2. Auth the sender via ``chat.auth.is_owner``. Unknown senders trigger the
   pairing flow (a code is generated and emailed back).
3. Build a ``run_turn`` call and let the agent process the message; the
   final response is the reply body.
4. Mark the message ``\\Seen`` and (if enabled) send the reply via SMTP.

Failures don't crash the poller — every message is wrapped so one bad
email doesn't stop the others from being processed.
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
import uuid
from email.message import EmailMessage
from email.utils import parseaddr

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage as DjEmailMessage

logger = logging.getLogger(__name__)


_REPLY_HEADER_RE = re.compile(r"^(?:>+ ?| {1,3})", re.MULTILINE)


def _connect():
    if not settings.EMAIL_IMAP_HOST:
        return None
    cls = imaplib.IMAP4_SSL if settings.EMAIL_IMAP_PORT == 993 else imaplib.IMAP4
    conn = cls(settings.EMAIL_IMAP_HOST, settings.EMAIL_IMAP_PORT)
    conn.login(settings.EMAIL_IMAP_USER, settings.EMAIL_IMAP_PASSWORD)
    conn.select(settings.EMAIL_IMAP_FOLDER)
    return conn


def _extract_text(msg: EmailMessage) -> str:
    """Return the best plain-text rendering of an email body."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.is_attachment():
                try:
                    return part.get_content().strip()
                except Exception:  # noqa: BLE001 -- fall through to next part
                    continue
        # No text/plain? Fall back to text/html → strip tags crudely.
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_content()
                except Exception:  # noqa: BLE001
                    continue
                return re.sub(r"<[^>]+>", "", html).strip()
        return ""
    try:
        return (msg.get_content() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _trim_reply_quotes(body: str) -> str:
    """Drop quoted-reply blocks ('> ...' lines and Outlook 'On ... wrote:' tails)."""
    if not body:
        return ""
    # Cut at common reply markers.
    for marker in (
        "\n-----Original Message-----",
        "\nOn ",  # "On <date>, <name> wrote:"
        "\nFrom: ",
    ):
        idx = body.find(marker)
        if idx != -1:
            body = body[:idx]
            break
    # Drop fully-quoted lines.
    lines = [ln for ln in body.splitlines() if not _REPLY_HEADER_RE.match(ln)]
    return "\n".join(lines).strip()


def _prompt_for_agent(sender: str, subject: str, body: str) -> str:
    return (
        f"You received this email and should respond.\n\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n\n"
        f"Body:\n{body or '(empty)'}\n\n"
        f"Write a concise reply. If the email is informational, just confirm receipt; "
        f"if it contains a request, take action or explain why you can't."
    )


def _send_reply(to: str, original_subject: str, body: str, in_reply_to: str = "") -> None:
    if not settings.EMAIL_REPLY_ENABLED:
        return
    if not to or not body:
        return
    subject = original_subject or "Re: your message"
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    msg = DjEmailMessage(subject=subject[:200], body=body[:8000], to=[to])
    if in_reply_to:
        msg.extra_headers = {"In-Reply-To": in_reply_to, "References": in_reply_to}
    msg.send(fail_silently=False)


def _start_pairing_email(sender: str, subject: str) -> None:
    """Generate a pairing code for an unknown email sender and reply with it."""
    try:
        from pairing.services import start_pairing
    except Exception as exc:  # noqa: BLE001
        logger.warning("pairing app unavailable: %s", exc)
        return
    pc = start_pairing("email", sender, display_name=sender)
    body = (
        "You're not on this assistant's allowlist yet.\n\n"
        f"Your pairing code is: {pc.code}\n\n"
        "Ask the owner to run:\n"
        f"    python manage.py pair approve {pc.code}\n\n"
        "Once approved, send your request again. This code expires in 1 hour."
    )
    try:
        _send_reply(sender, subject, body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to send pairing email to %s: %s", sender, exc)


def _handle_one(raw: bytes) -> tuple[str, str]:
    """Process one fetched email payload. Returns ``(status, summary)``."""
    msg: EmailMessage = email.message_from_bytes(raw, _class=EmailMessage)
    sender_full = msg.get("From", "")
    _, sender = parseaddr(sender_full)
    sender = (sender or "").lower()
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")

    if not sender:
        return "skip", "no sender"

    from chat.auth import is_owner

    if not is_owner("email", sender):
        _start_pairing_email(sender, subject)
        return "pairing", f"sent pairing code to {sender}"

    body = _trim_reply_quotes(_extract_text(msg))

    from agents.graph import run_turn

    session_id = f"email:{uuid.uuid4().hex[:12]}"
    try:
        reply = run_turn(
            session_id=session_id,
            message=_prompt_for_agent(sender, subject, body),
            source="email",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("email agent turn failed for %s", sender)
        return "error", str(exc)

    try:
        _send_reply(sender, subject, reply or "(no reply generated)", in_reply_to=message_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to deliver reply to %s: %s", sender, exc)
        return "reply-failed", str(exc)

    return "ok", f"replied to {sender} (subject={subject[:60]!r})"


@shared_task
def email_poll() -> int:
    """Celery beat task: fetch UNSEEN emails and process them. Returns count handled."""
    if not settings.EMAIL_IMAP_HOST:
        return 0

    handled = 0
    conn = None
    try:
        conn = _connect()
        if conn is None:
            return 0
        typ, data = conn.search(None, "UNSEEN")
        if typ != "OK":
            logger.warning("IMAP search failed: %s", data)
            return 0
        ids = (data[0] or b"").split()
        ids = ids[: settings.EMAIL_IMAP_POLL_LIMIT]
        for msg_id in ids:
            try:
                typ, payload = conn.fetch(msg_id, "(RFC822)")
                if typ != "OK" or not payload:
                    continue
                raw_body = payload[0][1] if isinstance(payload[0], tuple) else b""
                status, summary = _handle_one(raw_body)
                logger.info("email[%s] %s: %s", msg_id.decode(), status, summary)
                conn.store(msg_id, "+FLAGS", "\\Seen")
                handled += 1
            except Exception as exc:  # noqa: BLE001 -- per-message isolation
                logger.exception("email poll: failed on msg %s: %s", msg_id, exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass

    return handled
