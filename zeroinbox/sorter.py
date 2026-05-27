from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .classifier import classify, destination_map, ensure_classifier_ready
from .config import account_config, log_dir
from .imap_backend import ImapAccount
from .models import MailSummary, SortResult
from .report import write_pdf_report


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def classify_sample(config: dict[str, Any], account_name: str, subject: str, sender: str, body: str, classifier: str) -> dict[str, Any]:
    account = account_config(config, account_name)
    ensure_classifier_ready(config, classifier)
    mail = MailSummary(uid="sample", subject=subject, sender=sender, date="", body=body)
    decision = classify(config, account, mail, classifier)
    dest = destination_map(account)[decision.destination]
    return {
        "destination": decision.destination,
        "mailbox": dest.mailbox,
        "confidence": decision.confidence,
        "summary": decision.summary,
        "reason": decision.reason,
    }


def status(config: dict[str, Any], account_name: str | None = None) -> dict[str, Any]:
    account = account_config(config, account_name)
    with ImapAccount(account) as imap:
        count = imap.select_inbox()
        uids = imap.search_uids(limit=0)
    return {
        "account": account["name"],
        "host": account.get("host"),
        "inbox": account.get("inbox", "INBOX"),
        "search": account.get("search", "UNSEEN"),
        "inboxCount": count,
        "matchingCount": len(uids),
    }


def list_folders(config: dict[str, Any], account_name: str | None = None) -> dict[str, Any]:
    account = account_config(config, account_name)
    with ImapAccount(account) as imap:
        folders = imap.list_mailboxes()
    return {"account": account["name"], "folders": folders}


def sort_mail(config: dict[str, Any], account_name: str | None, limit: int, dry_run: bool, classifier: str | None) -> dict[str, Any]:
    account = account_config(config, account_name)
    ensure_classifier_ready(config, classifier)
    destinations = destination_map(account)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    records: list[dict[str, Any]] = []
    results: list[SortResult] = []
    moved = 0

    with ImapAccount(account) as imap:
        uids = imap.search_uids(limit=limit)
        for uid in uids:
            mail = imap.fetch_message(uid)
            decision = classify(config, account, mail, classifier)
            dest = destinations[decision.destination]
            action = "dry-run"
            if not dry_run:
                imap.move_uid(uid, dest.mailbox)
                action = "moved"
                moved += 1
            result = SortResult(
                uid=uid,
                subject=mail.subject,
                sender=mail.sender,
                date=mail.date,
                destination=decision.destination,
                mailbox=dest.mailbox,
                confidence=decision.confidence,
                summary=decision.summary,
                reason=decision.reason,
                action=action,
            )
            results.append(result)
            records.append(result.__dict__)
        if moved:
            imap.expunge()

    log_path = log_dir(config) / f"zeroinbox-{run_id}.jsonl"
    if records:
        write_jsonl(log_path, records)
    report_path = ""
    if results:
        report_path = str(write_pdf_report(config, run_id, account["name"], dry_run, moved, results))
    return {
        "runId": run_id,
        "account": account["name"],
        "dryRun": dry_run,
        "seen": len(results),
        "moved": moved,
        "logPath": str(log_path) if records else "",
        "reportPath": report_path,
        "results": [item.__dict__ for item in results],
    }
