from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zeroinbox.models import SortResult
from zeroinbox.config import load_config
from zeroinbox.report import write_pdf_report
from zeroinbox.cli import render_sort
from zeroinbox.sorter import sort_mail


def result(account: str, subject: str) -> SortResult:
    return SortResult(
        uid=subject,
        subject=subject,
        sender="sender@example.com",
        date="2026-06-15",
        destination="kommunikation",
        mailbox="INBOX/Archiv/Kommunikation",
        confidence=0.9,
        summary="Summary",
        reason="Reason",
        action="moved",
        source_account=account,
        source_mailbox="INBOX",
    )


class MultiAccountReportTests(unittest.TestCase):
    def test_openclaw_report_directory_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "workspace" / "ZEROINBOX"
            config = load_config(report_dir)
            path = write_pdf_report(
                config,
                "20260615-120000",
                "gmail / INBOX",
                False,
                1,
                [result("gmail", "Workspace report")],
            )
            self.assertEqual(path.parent, report_dir)

    def test_three_accounts_are_collected_into_one_report(self) -> None:
        accounts = [{"name": "gmail"}, {"name": "gmail_2"}, {"name": "icloud_3"}]
        first = result("gmail", "first")
        third = result("icloud_3", "third")
        payloads = [
            {
                "account": "gmail",
                "mailbox": "INBOX",
                "mailboxLabel": "INBOX",
                "target": "gmail / INBOX",
                "search": "UNSEEN",
                "seen": 1,
                "moved": 1,
                "records": [],
                "results": [first.__dict__],
                "_sortResults": [first],
            },
            {
                "account": "gmail_2",
                "mailbox": "INBOX",
                "mailboxLabel": "INBOX",
                "target": "gmail_2 / INBOX",
                "search": "UNSEEN",
                "seen": 0,
                "moved": 0,
                "records": [],
                "results": [],
                "_sortResults": [],
            },
            {
                "account": "icloud_3",
                "mailbox": "INBOX",
                "mailboxLabel": "INBOX",
                "target": "icloud_3 / INBOX",
                "search": "UNSEEN",
                "seen": 1,
                "moved": 1,
                "records": [],
                "results": [third.__dict__],
                "_sortResults": [third],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "REPORTS" / "report.pdf"
            with (
                patch("zeroinbox.sorter.mailbox_accounts", return_value=accounts),
                patch("zeroinbox.sorter.sort_one_mailbox", side_effect=payloads) as sort_one,
                patch("zeroinbox.sorter.write_pdf_report", return_value=report) as write_report,
            ):
                payload = sort_mail({"_baseDir": tmp}, None, False, None)

        self.assertEqual([call.args[1]["name"] for call in sort_one.call_args_list], ["gmail", "gmail_2", "icloud_3"])
        self.assertEqual([call.args[5] for call in sort_one.call_args_list], [0, 0, 0])
        self.assertEqual(payload["seen"], 2)
        self.assertEqual(payload["moved"], 2)
        self.assertEqual([item["seen"] for item in payload["mailboxes"]], [1, 0, 1])
        self.assertEqual(
            [item.source_account for item in write_report.call_args.args[5]],
            ["gmail", "icloud_3"],
        )
        text = render_sort(payload)
        self.assertIn("✅ gmail_2 / INBOX: no new mails, nothing to do.", text)
        self.assertIn(f"MEDIA:{report}", text)

    def test_pdf_accepts_multiple_accounts_and_control_characters(self) -> None:
        results = [
            result("gmail", "First\x00 subject"),
            result("icloud_2", "Second\x0b subject"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_pdf_report(
                {"_baseDir": tmp, "defaultModel": "test-model"},
                "20260615-120000",
                "gmail / INBOX, icloud_2 / INBOX",
                False,
                2,
                results,
            )
            self.assertTrue(path.is_file())
            self.assertTrue(path.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
