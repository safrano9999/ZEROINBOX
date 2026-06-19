#!/usr/bin/env bash
set -euo pipefail

repo="$(basename "$PWD")"
zip_name="${ZIP_NAME:-$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')-latest.zip}"
archive_list="${ARCHIVE_LIST:-/tmp/openclaw-plugin-archive-files.txt}"
deny_re='(^|/)(tag\.sh|\.env|\.calenv|\.gmail-oauth-client\.json|\.gmail-token.*\.json|\.venv|node_modules|__pycache__|logs|LOGS|state|REPORTS)(/|$)|(\.pyc|\.sqlite3)$'
include_list="$(mktemp)"
trap 'rm -f "$include_list"' EXIT

case "$repo" in
  DAILYNEWS) files=(README.md config.json openclaw.plugin.json package.json requirements.txt index.js generate.py scripts skills) ;;
  CALENDAR) files=(README.md CALENDAR_init.sh calendar_fetch.py config.json openclaw.plugin.json package.json requirements.txt index.js scripts) ;;
  ZEROINBOX) files=(README.md provider.conf ZEROINBOX_init.sh openclaw.plugin.json package.json requirements.txt index.js scripts skills zeroinbox) ;;
  KACHELMANN) files=(README.md config.json openclaw.plugin.json package.json requirements.txt requirements-mysql.txt requirements-postgres.txt index.js scripts kachelmann static templates webui.py) ;;
  *) echo "Unsupported OpenClaw plugin repo: $repo" >&2; exit 2 ;;
esac

rm -f "$zip_name" "$zip_name.sha256"
for path in "${files[@]}"; do
  [ -e "$path" ] || continue
  if [ -d "$path" ]; then
    find "$path" -type f | sort
  else
    printf '%s\n' "$path"
  fi
done | grep -Ev "$deny_re" > "$include_list"
for optional in env.example config.conf_example; do
  [ -f "$optional" ] && printf '%s\n' "$optional" >> "$include_list"
done
zip -q "$zip_name" -@ < "$include_list"
sha256sum "$zip_name" > "$zip_name.sha256"
zipinfo -1 "$zip_name" | tee "$archive_list"
if grep -E "$deny_re" "$archive_list"; then
  echo "Refusing to publish archive with dev helper, generated state, secrets, cache, or database files." >&2
  exit 1
fi
