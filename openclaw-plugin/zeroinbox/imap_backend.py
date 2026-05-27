from __future__ import annotations

import email
import email.policy
import imaplib
from contextlib import AbstractContextManager
from typing import Any

from .config import resolve_secret
from .models import MailSummary


def quote_mailbox(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def decode_body(msg: email.message.EmailMessage) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    parts.append(str(part.get_content()))
                except Exception:
                    continue
    elif msg.get_content_type() == "text/plain":
        try:
            parts.append(str(msg.get_content()))
        except Exception:
            pass
    if not parts:
        try:
            return str(msg.get_body(preferencelist=("plain", "html")).get_content())[:4000]
        except Exception:
            return ""
    return "\n\n".join(parts)[:4000]


def parse_message(uid: str, raw: bytes) -> MailSummary:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    return MailSummary(
        uid=uid,
        subject=str(msg.get("Subject", "")),
        sender=str(msg.get("From", "")),
        date=str(msg.get("Date", "")),
        body=decode_body(msg),
    )


class ImapAccount(AbstractContextManager["ImapAccount"]):
    def __init__(self, account: dict[str, Any]):
        self.account = account
        self.conn: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> "ImapAccount":
        host = str(self.account.get("host") or "")
        port = int(self.account.get("port") or 993)
        username = resolve_secret(self.account, "username")
        password = resolve_secret(self.account, "password")
        if not host or not username or not password:
            raise RuntimeError("IMAP host, username or password is missing.")
        self.conn = imaplib.IMAP4_SSL(host, port)
        self.conn.login(username, password)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.conn:
            return
        try:
            self.conn.close()
        except Exception:
            pass
        try:
            self.conn.logout()
        except Exception:
            pass

    @property
    def imap(self) -> imaplib.IMAP4_SSL:
        if not self.conn:
            raise RuntimeError("IMAP connection is not open.")
        return self.conn

    def select_inbox(self) -> int:
        inbox = str(self.account.get("inbox") or "INBOX")
        status, data = self.imap.select(quote_mailbox(inbox))
        if status != "OK":
            raise RuntimeError(f"Cannot select mailbox {inbox}: {data}")
        try:
            return int(data[0] or 0)
        except Exception:
            return 0

    def search_uids(self, limit: int) -> list[str]:
        self.select_inbox()
        criteria = str(self.account.get("search") or "UNSEEN").strip() or "UNSEEN"
        status, data = self.imap.uid("SEARCH", None, *criteria.split())
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {data}")
        uids = data[0].decode("ascii", errors="ignore").split() if data and data[0] else []
        if limit > 0:
            return uids[:limit]
        return uids

    def fetch_message(self, uid: str) -> MailSummary:
        # BODY.PEEK[] fetches the message body without setting Gmail's \Seen flag.
        status, data = self.imap.uid("FETCH", uid, "(BODY.PEEK[])")
        if status != "OK":
            raise RuntimeError(f"IMAP fetch failed for UID {uid}: {data}")
        for item in data:
            if isinstance(item, tuple) and isinstance(item[1], bytes):
                return parse_message(uid, item[1])
        raise RuntimeError(f"IMAP fetch returned no message for UID {uid}.")

    def ensure_mailbox(self, mailbox: str) -> None:
        if not self.account.get("createMissingFolders", True):
            return
        status, _ = self.imap.create(quote_mailbox(mailbox))
        if status not in {"OK", "NO"}:
            raise RuntimeError(f"Could not create mailbox {mailbox}.")

    def move_uid(self, uid: str, mailbox: str) -> None:
        self.ensure_mailbox(mailbox)
        status, data = self.imap.uid("COPY", uid, quote_mailbox(mailbox))
        if status != "OK":
            raise RuntimeError(f"IMAP copy failed for UID {uid} to {mailbox}: {data}")
        status, data = self.imap.uid("STORE", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise RuntimeError(f"IMAP delete flag failed for UID {uid}: {data}")

    def expunge(self) -> None:
        if self.account.get("expungeAfterMove", True):
            self.imap.expunge()

    def list_mailboxes(self) -> list[str]:
        status, data = self.imap.list()
        if status != "OK":
            raise RuntimeError(f"IMAP list failed: {data}")
        result: list[str] = []
        for raw in data or []:
            if not raw:
                continue
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            result.append(text)
        return result
