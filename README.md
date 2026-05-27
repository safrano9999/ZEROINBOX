# ZEROINBOX

OpenClaw-ready IMAP mail sorter with LiteLLM classification and PDF reports.

Runtime code lives in the repository root. The OpenClaw plugin starts the
Python CLI directly; OpenClaw does not classify mails and does not touch the
LiteLLM decision logic.

## What It Does

- reads IMAP mail from the configured account
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

## Install From Checkout

```bash
openclaw plugins install --link /home/openclaw/safcontainer/ZEROINBOX \
  --dangerously-force-unsafe-install
openclaw gateway restart
```

## Release Zip

GitHub Actions builds the installable zip from the repository root when a
manual date tag is pushed. Use the `YYYY.M.D` convention without leading
zeroes, for example `2026.5.27`. The same build also overwrites the moving
`latest` release.

Download example:

```bash
gh release download 2026.5.27 \
  --repo safrano9999/ZEROINBOX \
  --pattern 'zeroinbox-latest.zip'

gh release download latest \
  --repo safrano9999/ZEROINBOX \
  --pattern 'zeroinbox-latest.zip'
```
