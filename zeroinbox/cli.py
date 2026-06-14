from __future__ import annotations

import argparse
import json
import shlex
import sys
from typing import Any

from .classifier import destination_list
from .config import account_config, load_config
from .sorter import classify_sample, list_folders, sort_mail, status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ZEROINBOX standalone mail sorter")
    parser.add_argument("--config", default="config.conf", help="Path to config.conf")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--raw", default="", help="Raw OpenClaw slash-command args")
    sub = parser.add_subparsers(dest="command")

    p_status = sub.add_parser("status", help="Connect and count matching messages")
    p_status.add_argument("--account", default=None)

    p_folders = sub.add_parser("folders", help="List IMAP folders")
    p_folders.add_argument("--account", default=None)

    p_sort = sub.add_parser("sort", help="Classify and optionally move messages")
    p_sort.add_argument("--account", default=None)
    p_sort.add_argument("--dry-run", action="store_true")
    p_sort.add_argument("--commit", action="store_true", help="Actually move messages")
    p_sort.add_argument("--classifier", choices=["litellm", "rules"], default=None)

    p_classify = sub.add_parser("classify-test", help="Classify supplied text without IMAP")
    p_classify.add_argument("--account", default=None)
    p_classify.add_argument("--subject", default="")
    p_classify.add_argument("--from", dest="sender", default="")
    p_classify.add_argument("--body", default="")
    p_classify.add_argument("--classifier", choices=["litellm", "rules"], default="rules")

    p_config = sub.add_parser("config", help="Show sanitized config summary")
    p_config.add_argument("--account", default=None)

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    initial = build_parser().parse_args(argv)
    if initial.raw.strip():
        raw_args = shlex.split(initial.raw)
        return build_parser().parse_args(["--config", initial.config, "--json", *raw_args])
    return initial


def render_sort(payload: dict[str, Any]) -> str:
    mailboxes = payload.get("mailboxes") if isinstance(payload.get("mailboxes"), list) else []
    if mailboxes:
        empty = [item for item in mailboxes if int(item.get("seen") or 0) == 0]
        active = [item for item in mailboxes if int(item.get("seen") or 0) > 0]
        if payload["seen"] == 0:
            return "\n".join(f"✅ {item.get('target')}: no new mails, nothing to do." for item in empty)
        mode = "dry-run" if payload["dryRun"] else "commit"
        lines = [
            f"ZEROINBOX: {payload['seen']} Mails verarbeitet ({mode}), {payload['moved']} verschoben.",
        ]
        lines.extend(
            f"- {item.get('target')}: {item.get('seen')} Mails, {item.get('moved')} verschoben"
            for item in active
        )
        lines.extend(f"✅ {item.get('target')}: no new mails, nothing to do." for item in empty)
        for item in payload["results"][:10]:
            lines.append(
                f"- {item['destination']} -> {item['subject'][:90]} ({item['action']}, {item['confidence']:.2f})"
            )
        if payload.get("logPath"):
            lines.append(f"Log: {payload['logPath']}")
        if payload.get("reportPath"):
            lines.append(f"PDF: {payload['reportPath']}")
            lines.append(f"MEDIA:{payload['reportPath']}")
        return "\n".join(lines)
    mailbox = payload.get("mailbox") or "INBOX"
    target = f"{payload['account']} / {mailbox}"
    if payload["seen"] == 0:
        return f"✅ ZEROINBOX {target}: no new mails, nothing to do."
    mode = "dry-run" if payload["dryRun"] else "commit"
    lines = [
        f"ZEROINBOX {target}: {payload['seen']} Mails verarbeitet ({mode}), {payload['moved']} verschoben.",
    ]
    for item in payload["results"][:10]:
        lines.append(
            f"- {item['destination']} -> {item['subject'][:90]} ({item['action']}, {item['confidence']:.2f})"
        )
    if payload.get("logPath"):
        lines.append(f"Log: {payload['logPath']}")
    if payload.get("reportPath"):
        lines.append(f"PDF: {payload['reportPath']}")
        lines.append(f"MEDIA:{payload['reportPath']}")
    return "\n".join(lines)


def render(payload: dict[str, Any]) -> str:
    kind = payload.get("kind")
    if kind == "status":
        return (
            f"ZEROINBOX {payload['account']}: {payload['matchingCount']} passende Mails "
            f"bei Suche {payload['search']} in {payload['inbox']} ({payload['inboxCount']} total)."
        )
    if kind == "folders":
        folders = "\n".join(f"- {item}" for item in payload["folders"][:40])
        return f"ZEROINBOX {payload['account']} folders:\n{folders}"
    if kind == "sort":
        return render_sort(payload)
    if kind == "classify-test":
        return (
            f"ZEROINBOX classify-test: {payload['destination']} -> {payload['mailbox']} "
            f"({payload['confidence']:.2f})\n{payload['reason']}"
        )
    if kind == "config":
        return (
            f"ZEROINBOX config: account={payload['account']} host={payload['host']} "
            f"destinations={payload['destinations']} defaultDryRun={payload['defaultDryRun']}"
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def command_payload(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    command = args.command or "status"
    if command == "status":
        payload = status(config, args.account)
        payload["kind"] = "status"
        return payload
    if command == "folders":
        payload = list_folders(config, args.account)
        payload["kind"] = "folders"
        return payload
    if command == "sort":
        default_dry = bool(config.get("defaultDryRun", True))
        dry_run = True if args.dry_run else default_dry
        if args.commit:
            dry_run = False
        payload = sort_mail(config, args.account, dry_run, args.classifier)
        payload["kind"] = "sort"
        return payload
    if command == "classify-test":
        payload = classify_sample(config, args.account, args.subject, args.sender, args.body, args.classifier)
        payload["kind"] = "classify-test"
        return payload
    if command == "config":
        account = account_config(config, args.account)
        return {
            "kind": "config",
            "account": account["name"],
            "host": account.get("host"),
            "destinations": len(destination_list(account)),
            "defaultDryRun": bool(config.get("defaultDryRun", True)),
        }
    raise ValueError(f"Unknown command: {command}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = command_payload(args)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload["ok"] = True
    payload["text"] = render(payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(payload["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
