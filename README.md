# ZEROINBOX

[![OpenClaw plugin build](https://github.com/safrano9999/ZEROINBOX/actions/workflows/openclaw-plugin-release.yml/badge.svg)](https://github.com/safrano9999/ZEROINBOX/actions/workflows/openclaw-plugin-release.yml)

> **Type:** standalone Python IMAP sorter with an optional OpenClaw adapter.
> **OpenClaw:** supported through the release ZIP.
> **Hermes:** no Hermes adapter is included.

ZEROINBOX reads one or more IMAP inboxes, classifies matching messages through
an OpenAI-v1-compatible endpoint, optionally moves them into an explicit folder
allowlist, and produces JSONL and PDF reports.

The Python application owns all IMAP and classification behavior. OpenClaw is
only an adapter around that application; it does not classify messages itself.

## Releases

This is a private repository. An authorized GitHub login is required to view
the release page or download its assets.

- [Latest release](https://github.com/safrano9999/ZEROINBOX/releases/latest)
- [OpenClaw plugin ZIP: `zeroinbox-latest.zip`](https://github.com/safrano9999/ZEROINBOX/releases/download/latest/zeroinbox-latest.zip)
  · [SHA-256](https://github.com/safrano9999/ZEROINBOX/releases/download/latest/zeroinbox-latest.zip.sha256)

The ZIP is an OpenClaw plugin package, not a generic bare-metal installer.
Use a source checkout for bare-metal operation. Generated ZIP files are release
assets and are not stored in the repository.

Download and verify the current plugin:

```bash
gh auth login
gh release download latest --repo safrano9999/ZEROINBOX \
  --pattern 'zeroinbox-latest.zip*' --clobber
sha256sum -c zeroinbox-latest.zip.sha256
```

## Features

- IMAP over TLS with built-in defaults for Gmail and iCloud
- Case-insensitive custom IMAP providers
- Up to 50 independently configured accounts
- Sequential multi-account processing and one combined PDF report
- OpenAI-v1 classification with configurable model, endpoint, key, and
  streaming mode
- Conservative fixed destination allowlist with an `uncertain` fallback
- Non-LLM rules classifier for mechanics tests
- Dry-run and committed move modes
- JSON output for automation and human-readable CLI output
- OpenClaw command, tool, authenticated webhook, and optional outbound delivery

## Deployment modes

| Mode | Status | What runs |
| --- | --- | --- |
| Bare metal | Supported | The Python CLI runs directly from a source checkout. |
| OpenClaw | Optional, supported | The release ZIP registers `/zeroinbox`, `zeroinbox_run`, and an authenticated webhook. |
| Hermes | Not included | This repository has no Hermes plugin or Hermes tool registration. |

## Bare-metal installation

Requirements:

- Python 3 with `venv`
- IMAP credentials or provider-specific app passwords
- an OpenAI-v1-compatible endpoint for normal classification

```bash
git clone https://github.com/safrano9999/ZEROINBOX.git
cd ZEROINBOX
scripts/setup-python.sh
./ZEROINBOX_init.sh
```

The interactive initializer writes account credentials and settings to the
ignored `.env` file with mode `0600`. Run it again, or pass `--new`, to add the
next account slot.

Start with a non-mutating check:

```bash
.venv/bin/python -m zeroinbox.cli config
.venv/bin/python -m zeroinbox.cli status
.venv/bin/python -m zeroinbox.cli folders
.venv/bin/python -m zeroinbox.cli sort --dry-run --limit 10
```

Move messages only after the dry-run output and target folders are correct:

```bash
.venv/bin/python -m zeroinbox.cli sort --commit
```

Without `--account`, a sort processes every configured account in order. Use
`--account gmail`, for example, to select one account.

## Configuration

ZEROINBOX runtime values are loaded from process environment variables and the
ignored `.env` file. Static built-in provider defaults live in `provider.conf`.

### Mail accounts

The first account has no suffix:

```env
ZEROINBOX_PROVIDER=gmail
ZEROINBOX_EMAIL=person@example.com
ZEROINBOX_APP_PASSWORD=replace-with-an-app-password
ZEROINBOX_ONLY_UNSEEN=1
```

Additional accounts use `_2`, `_3`, and so on:

```env
ZEROINBOX_PROVIDER_2=icloud
ZEROINBOX_EMAIL_2=person@icloud.com
ZEROINBOX_APP_PASSWORD_2=replace-with-an-app-password
ZEROINBOX_ONLY_UNSEEN_2=1
```

For a provider not present in `provider.conf`, define its connection settings:

```env
ZEROINBOX_PROVIDER_3=work
ZEROINBOX_PROVIDER_WORK_URL=outlook.office365.com
ZEROINBOX_PROVIDER_WORK_PORT=993
ZEROINBOX_PROVIDER_WORK_INBOX=INBOX
ZEROINBOX_PROVIDER_WORK_ARCHIVE_PREFIX=ZEROINBOX/Archiv
ZEROINBOX_EMAIL_3=person@example.com
ZEROINBOX_APP_PASSWORD_3=replace-with-an-app-password
```

Provider names are case-insensitive. The initializer can create these entries
interactively.

### OpenAI-v1 classification

```env
ZEROINBOX_OPENAI_V1_DEFAULT_LLM=luna
OPENAI_V1_PROVIDER=litellm
OPENAI_V1_URL=http://127.0.0.1
OPENAI_V1_PORT=4000
OPENAI_V1_KEY=replace-with-a-bearer-key
OPENAI_V1_STREAM=true
```

If the URL has no path, ZEROINBOX adds `/v1`. Keep `OPENAI_V1_STREAM=true` for
endpoints such as `luna` through LiteLLM that require streamed completions; set
it to `false` only for an endpoint that does not support streaming. Streamed
text is accumulated in memory, parsed as the same strict four-field JSON
object, then the mutable buffer is cleared and the stream is closed.

The classifier accepts exactly these fields:

```json
{
  "destination": "uncertain",
  "confidence": 0.5,
  "summary": "Short summary",
  "reason": "Classification reason"
}
```

Unknown fields, duplicate fields, wrappers, or unknown destinations are
rejected or normalized to the conservative fallback.

For a local mechanics test that sends no message content to an LLM:

```bash
.venv/bin/python -m zeroinbox.cli classify-test \
  --classifier rules \
  --subject 'Invoice 123' \
  --from billing@example.com
```

### Destination folders

The built-in destinations include communication, newsletters, system messages,
payments, terms, welcome mail, disposable mail, and uncertain mail. Their
actual mailbox paths are derived from each provider's archive prefix.

Create the configured folders before the first committed sort:

```bash
scripts/gmail-init-labels
```

The default path uses IMAP and the account password. Gmail API credentials are
needed only when `ZEROINBOX_LABEL_METHOD=gmail-api` is selected.

## OpenClaw plugin

Install the verified release archive:

```bash
openclaw plugins install ./zeroinbox-latest.zip \
  --force --dangerously-force-unsafe-install
openclaw gateway restart
```

The plugin creates its own `.venv` on first use unless `autoSetupPython` is
disabled. Mail and OpenAI-v1 variables must be available to the gateway process
or in a `.env` file in the installed plugin directory.

Registered interfaces:

- slash command: `/zeroinbox`
- tool: `zeroinbox_run`
- gateway-auth route: `POST /plugins/zeroinbox/run`

Examples:

```text
/zeroinbox
/zeroinbox status
/zeroinbox folders
/zeroinbox sort --dry-run
/zeroinbox sort --commit
```

An empty command and the default webhook both run `sort --commit`. Change
`defaultArgs` or `webhook.args` in the OpenClaw plugin configuration if a
different default is required.

Webhook example:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}" \
  "http://127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18789}/plugins/zeroinbox/run"
```

The optional `delivery` plugin configuration can send the result and PDF
through an OpenClaw outbound channel:

```json
{
  "plugins": {
    "entries": {
      "zeroinbox": {
        "enabled": true,
        "config": {
          "defaultArgs": "sort --commit",
          "webhook": {
            "enabled": true,
            "path": "/plugins/zeroinbox/run",
            "args": "sort --commit"
          },
          "delivery": {
            "channel": "telegram",
            "target": "replace-with-chat-id"
          }
        }
      }
    }
  }
}
```

Scheduling is owned by the host or OpenClaw cron. ZEROINBOX does not contain an
internal scheduler.

For linked plugin development:

```bash
openclaw plugins install --link "$(pwd)" \
  --dangerously-force-unsafe-install
openclaw gateway restart
```

## Storage and backups

ZEROINBOX keeps no local message database. Messages remain on the IMAP server
and committed runs move them between server-side mailboxes.

Local runtime data:

- `.env`: credentials, account behavior, and persistence switches
- `logs/`: JSONL decisions for processed messages
- `REPORTS/`: combined PDF reports
- `.venv/`: reproducible local Python environment, safe to recreate

Container configuration can map `logs/` and `REPORTS/` to named volumes through
the switches in `env.example`. Back up the configuration and whichever
report/log history you intend to retain.

## Security

- Use provider-specific app passwords instead of primary account passwords.
- Protect `.env`, logs, and reports; they contain sensitive account or message
  metadata.
- A normal LLM classification sends sender, date, subject, and up to 4,000
  characters of message body to the configured OpenAI-v1 endpoint.
- Test with `--dry-run`; `--commit` performs real IMAP moves.
- Keep the OpenClaw webhook behind gateway authentication.
- Use a private or TLS-protected endpoint for any remote OpenAI-v1 service.
- Raw streamed completion chunks and full message bodies are not written to the
  decision log by the classifier.

## Operations

Useful diagnostics:

```bash
.venv/bin/python -m zeroinbox.cli --json config
.venv/bin/python -m zeroinbox.cli --json status
.venv/bin/python -m zeroinbox.cli --json folders
.venv/bin/python -m zeroinbox.cli sort --dry-run --limit 1
```

Each non-empty multi-account run produces one report: an overview followed by
one page per processed message, in account order. OpenClaw responses expose the
PDF as media when one was generated.

## Development

The repository contains the standalone Python package and the OpenClaw adapter
in the same source tree.

```bash
scripts/setup-python.sh
scripts/check.sh
.venv/bin/python -m unittest discover -s tests
```

`scripts/check.sh` requires Node.js for `index.js` syntax checking and Python
for bytecode compilation. Release ZIP construction is performed by the
repository's GitHub Actions workflow; generated archives are never committed.
