from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .classifier import classify, destination_map, ensure_classifier_ready
from .config import account_config, log_dir, mailbox_accounts
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


def mailbox_label(account: dict[str, Any]) -> str:
    return f"{account['name']} / {account.get('mailboxLabel') or account.get('inbox') or 'INBOX'}"


def sort_one_mailbox(
    config: dict[str, Any],
    account: dict[str, Any],
    limit: int,
    dry_run: bool,
    classifier: str | None,
    run_id: str,
) -> dict[str, Any]:
    destinations = destination_map(account)
    records: list[dict[str, Any]] = []
    results: list[SortResult] = []
    moved = 0

    with ImapAccount(account) as imap:
        uids = imap.search_uids(limit=limit)
        if uids:
            ensure_classifier_ready(config, classifier)
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
            record = dict(result.__dict__)
            record["sourceAccount"] = account["name"]
            record["sourceMailbox"] = str(account.get("inbox") or "INBOX")
            records.append(record)
        if moved:
            imap.expunge()

    return {
        "account": account["name"],
        "mailbox": str(account.get("inbox") or "INBOX"),
        "mailboxLabel": str(account.get("mailboxLabel") or account.get("inbox") or "INBOX"),
        "target": mailbox_label(account),
        "search": str(account.get("search") or "UNSEEN"),
        "seen": len(results),
        "moved": moved,
        "records": records,
        "results": [item.__dict__ for item in results],
        "_sortResults": results,
    }


def sort_mail(config: dict[str, Any], account_name: str | None, limit: int, dry_run: bool, classifier: str | None) -> dict[str, Any]:
    accounts = mailbox_accounts(config, account_name)
    if not accounts:
        raise ValueError("No ZEROINBOX accounts configured.")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    mailbox_payloads = [sort_one_mailbox(config, account, limit, dry_run, classifier, run_id) for account in accounts]
    records = [record for payload in mailbox_payloads for record in payload["records"]]
    sort_results = [result for payload in mailbox_payloads for result in payload["_sortResults"]]
    moved = sum(int(payload["moved"]) for payload in mailbox_payloads)

    log_path = log_dir(config) / f"zeroinbox-{run_id}.jsonl"
    if records:
        write_jsonl(log_path, records)
    report_path = ""
    if sort_results:
        active_sources = ", ".join(payload["target"] for payload in mailbox_payloads if payload["seen"])
        report_path = str(write_pdf_report(config, run_id, active_sources, dry_run, moved, sort_results))
    visible_payloads = [
        {key: value for key, value in payload.items() if key not in {"records", "_sortResults"}}
        for payload in mailbox_payloads
    ]
    first = visible_payloads[0]
    return {
        "runId": run_id,
        "account": first["account"],
        "mailbox": first["mailbox"],
        "search": first["search"],
        "dryRun": dry_run,
        "seen": len(sort_results),
        "moved": moved,
        "logPath": str(log_path) if records else "",
        "reportPath": report_path,
        "results": [record for payload in visible_payloads for record in payload["results"]],
        "mailboxes": visible_payloads,
    }
