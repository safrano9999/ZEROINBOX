# ZEROINBOX

[![OpenClaw plugin](https://github.com/safrano9999/ZEROINBOX/actions/workflows/openclaw-plugin-release.yml/badge.svg)](https://github.com/safrano9999/ZEROINBOX/actions/workflows/openclaw-plugin-release.yml)

**Download (always the latest CI build):**
[`zeroinbox-latest.zip`](https://github.com/safrano9999/ZEROINBOX/releases/download/latest/zeroinbox-latest.zip)
· [`.sha256`](https://github.com/safrano9999/ZEROINBOX/releases/download/latest/zeroinbox-latest.zip.sha256)

OpenClaw-ready IMAP mail sorter with LiteLLM classification and PDF reports.

Runtime code lives in the repository root. The OpenClaw plugin starts the
Python CLI directly; OpenClaw does not classify mails and does not touch the
LiteLLM decision logic.

## What It Does

- reads IMAP mail from the configured account
- checks all configured accounts/mailboxes in the normal sort flow
- classifies matching messages with `litellm.completion(...)`
- moves messages into configured folders when run with `--commit`
- writes JSONL decisions to `logs/`
- writes a PDF report to `REPORTS/`

The PDF keeps the known ZEROINBOX layout: colored overview first, then one page
per processed email.

## OpenClaw

The plugin registers:

- tool: `zeroinbox_run`
- slash command: `/zeroinbox`
- webhook: `POST /plugins/zeroinbox/run`

Examples:

```text
/zeroinbox
/zeroinbox status
/zeroinbox folders
/zeroinbox sort --dry-run --limit 10
/zeroinbox sort --commit --limit 10
```

By default `/zeroinbox` and the webhook run:

```text
sort --commit --limit 10
```

Sort responses include `MEDIA:<pdf path>` when a PDF was generated, so Telegram
receives the report through OpenClaw.
When all checked mailboxes are empty, the response lists every mailbox with a
green check and no PDF is generated. If only some mailboxes have work, the empty
ones are still listed in the text response and only processed mails appear in
the PDF.

On this host the OpenClaw cron jobs run it at `10:00` and `20:00`
(`Europe/Vienna`).

## Config

Main config:

```text
config.json
```

Credentials belong in an ignored dotenv file next to that config, usually:

```text
.env
```

Required Gmail IMAP values:

```env
ZEROINBOX_GMAIL_USERNAME=dummy@example.com
ZEROINBOX_GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
```

LiteLLM is called by ZEROINBOX itself. For the local LiteLLM proxy:

```env
LITELLM_API_KEY=...
LITELLM_URL=https://forky.tailb13f39.ts.net
LITELLM_PORT=888
ZEROINBOX_MODEL=gemini/gemini-flash-lite-latest
```

Multiple source mailboxes can be configured per account:

```json
{
  "accounts": {
    "gmail": {
      "inbox": "INBOX",
      "search": "UNSEEN",
      "mailboxes": [
        "INBOX",
        { "label": "Updates", "inbox": "INBOX/Updates", "search": "UNSEEN" }
      ]
    }
  }
}
```

Without `--account`, `sort` checks every configured account and every listed
mailbox. With `--account gmail`, it checks all mailboxes for that account.

## Gmail Labels

Create the configured target labels before the first committed sort:

```bash
cd /home/openclaw/safcontainer/ZEROINBOX
scripts/gmail-init-labels
```

Default label creation uses Gmail IMAP and the app password. Google Cloud OAuth
JSON is only needed if `ZEROINBOX_LABEL_METHOD=gmail-api` is set.

## Local Check

```bash
cd /home/openclaw/safcontainer/ZEROINBOX
scripts/check.sh
```

Direct CLI run for debugging:

```bash
scripts/setup-python.sh
.venv/bin/python -m zeroinbox.cli \
  --config config.json \
  sort --dry-run --limit 10
```

## Install

Install or update to the latest CI build — one flow, always tracks `latest`:

```bash
gh release download latest --repo safrano9999/ZEROINBOX \
  --pattern 'zeroinbox-latest.zip*' --clobber
sha256sum -c zeroinbox-latest.zip.sha256
openclaw plugins install ./zeroinbox-latest.zip --force --dangerously-force-unsafe-install
openclaw gateway restart
```

The `latest` release always points at the newest CI build, so this never needs a
version bump. The plugin creates `.venv` on first run unless `autoSetupPython`
is disabled.

Local dev (clone + link, runs in place):

```bash
git clone https://github.com/safrano9999/ZEROINBOX.git
cd ZEROINBOX
openclaw plugins install --link "$(pwd)" \
  --dangerously-force-unsafe-install
openclaw gateway restart
```
