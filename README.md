# ZEROINBOX

[![OpenClaw plugin](https://github.com/safrano9999/ZEROINBOX/actions/workflows/openclaw-plugin-release.yml/badge.svg)](https://github.com/safrano9999/ZEROINBOX/actions/workflows/openclaw-plugin-release.yml)

**Download (always the latest CI build):**
[`zeroinbox-latest.zip`](https://github.com/safrano9999/ZEROINBOX/releases/download/latest/zeroinbox-latest.zip)
· [`.sha256`](https://github.com/safrano9999/ZEROINBOX/releases/download/latest/zeroinbox-latest.zip.sha256)

OpenClaw-ready IMAP mail sorter with OpenAI-v1 classification and PDF reports.

Runtime code lives in the repository root. The OpenClaw plugin starts the
Python CLI directly; OpenClaw does not classify mails and does not touch the
OpenAI-v1 decision logic.

## What It Does

- reads IMAP mail from the configured account
- checks all configured accounts/mailboxes in the normal sort flow
- classifies matching messages with the official OpenAI Python client
- moves messages into configured folders when run with `--commit`
- writes JSONL decisions to `logs/`
- writes a PDF report to `REPORTS/` on bare metal
- writes reports to `REPORTS/` relative to the ZEROINBOX directory

The PDF keeps the known ZEROINBOX layout: colored overview first, then one page
per processed email.

## OpenClaw

The plugin registers:

- tool: `zeroinbox_run`
- slash command: `/zeroinbox`
- webhook: `POST /plugins/zeroinbox/run`

Enter this to trigger webhook from inside container:
```bash
curl -sS -X POST -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}" "http://127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18789}/plugins/zeroinbox/run"
```

Examples:

```text
/zeroinbox
/zeroinbox status
/zeroinbox folders
/zeroinbox sort --dry-run
/zeroinbox sort --commit
```

By default `/zeroinbox` and the webhook run:

```text
sort --commit
```

Sort responses include `MEDIA:<pdf path>` when a PDF was generated, so Telegram
receives the report through OpenClaw.
Accounts are checked one after another. Empty accounts produce one green-check
line. Results from every non-empty account are appended to one PDF in account
order; its overview comes first and every processed email gets its own page.
Mixed runs return both the green-check text and the PDF.

On this host the OpenClaw cron jobs run it at `10:00` and `20:00`
(`Europe/Vienna`).

## Config

Versioned provider defaults:

```text
provider.conf
```

Local account/runtime values belong in the ignored dotenv file:

```text
.env
```

Accounts are added by the init script. It writes provider, address, password
and custom provider connection values to `.env`; running it again appends the
next slot (`_2`, `_3`, ...).

```bash
./ZEROINBOX_init.sh
```

Single Gmail account after init:

```env
ZEROINBOX_PROVIDER=gmail
ZEROINBOX_EMAIL=dummy@example.com
ZEROINBOX_APP_PASSWORD=xxxxxxxxxxxxxxxx
```

OpenAI-v1 classification is called by ZEROINBOX itself. For a local compatible proxy:

```env
ZEROINBOX_OPENAI_V1_DEFAULT_LLM=gemini/gemini-flash-lite-latest
OPENAI_V1_PROVIDER=
OPENAI_V1_KEY=...
OPENAI_V1_URL=https://forky.tailb13f39.ts.net
OPENAI_V1_PORT=888
OPENAI_V1_STREAM=false
```

Set `OPENAI_V1_STREAM=true` for providers such as ChatGPT subscription OAuth
that only produce a usable completion through streaming. ZEROINBOX consumes
only text deltas in memory, never logs or persists raw chunks, and accepts only
the exact classification JSON fields.

Known providers are read from `provider.conf`; currently `gmail` and `icloud`.
Provider names are case-insensitive. A custom provider entered in
`ZEROINBOX_init.sh` writes the matching connection values to `.env`:

```env
ZEROINBOX_PROVIDER_2=ms
ZEROINBOX_PROVIDER_MS_URL=outlook.office365.com
ZEROINBOX_PROVIDER_MS_PORT=993
ZEROINBOX_EMAIL_2=dummy@outlook.com
ZEROINBOX_APP_PASSWORD_2=xxxxxxxxxxxxxxxx
```

Without `--account`, `sort` checks every configured account. With
`--account gmail`, it checks only that provider account.

## Account Folders

Create the configured target folders before the first committed sort:

```bash
cd /home/openclaw/safcontainer/ZEROINBOX
scripts/gmail-init-labels
```

Default folder creation uses IMAP and the app password. Google Cloud OAuth JSON
is only needed if `ZEROINBOX_LABEL_METHOD=gmail-api` is set for Gmail.

In the `safrano9999-openclaw` container this label init is run once at container
startup for all configured accounts.

## Local Check

```bash
cd /home/openclaw/safcontainer/ZEROINBOX
scripts/check.sh
```

Direct CLI run for debugging:

```bash
scripts/setup-python.sh
set -a; . ./.env; set +a
.venv/bin/python -m zeroinbox.cli sort --dry-run
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
