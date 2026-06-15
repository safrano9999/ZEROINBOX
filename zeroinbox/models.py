from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    key: str
    mailbox: str
    description: str = ""


@dataclass(frozen=True)
class MailSummary:
    uid: str
    subject: str
    sender: str
    date: str
    body: str


@dataclass(frozen=True)
class Decision:
    destination: str
    confidence: float
    summary: str
    reason: str


@dataclass(frozen=True)
class SortResult:
    uid: str
    subject: str
    sender: str
    date: str
    destination: str
    mailbox: str
    confidence: float
    summary: str
    reason: str
    action: str
    source_account: str = ""
    source_mailbox: str = ""
