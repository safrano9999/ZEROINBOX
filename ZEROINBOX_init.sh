#!/usr/bin/env python3
"""ZEROINBOX account init.

This script is intentionally only about account config:
- provider/account metadata goes to config.conf
- mail address/password go to .env
- folder/label creation is handled separately by scripts/gmail-init-labels
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.conf"
ENV_PATH = ROOT_DIR / ".env"


def ask(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{question}{suffix}: ").strip()
    return value or default


def ask_choice(question: str, options: tuple[str, ...], default: str) -> str:
    pretty = "/".join(options)
    while True:
        value = ask(f"{question} ({pretty})", default).lower()
        if value in options:
            return value


def read_kv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def upsert_kv(path: Path, updates: dict[str, str], mode: int | None = None) -> None:
    lines: list[str] = []
    seen: set[str] = set()
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                lines.append(raw)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                seen.add(key)
            else:
                lines.append(raw)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def provider_conf_path() -> Path | None:
    candidates = [
        ROOT_DIR / "provider.conf",
        ROOT_DIR / "safrano9999" / "zeroinbox-provider.conf",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def provider_names() -> list[str]:
    path = provider_conf_path()
    if not path:
        return []
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        match = re.match(r"^\[provider\.([^]]+)\]$", line, re.I)
        if match:
            names.append(match.group(1).strip().lower())
    return sorted(set(names))


def provider_token(provider: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", provider.upper()).strip("_")


def suffix_for_index(index: int) -> str:
    return "" if index == 1 else f"_{index}"


def env_key(base: str, suffix: str) -> str:
    return f"ZEROINBOX_{base}{suffix}"


def provider_key(suffix: str) -> str:
    return env_key("PROVIDER", suffix)


def account_name(provider: str, suffix: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", provider.lower()).strip("_") or "account"
    return normalized if not suffix else f"{normalized}{suffix}"


def first_free_or_incomplete_slot(conf: dict[str, str], env: dict[str, str]) -> str:
    for index in range(1, 51):
        suffix = suffix_for_index(index)
        has_provider = bool(conf.get(provider_key(suffix)))
        has_email = bool(env.get(env_key("EMAIL", suffix)))
        has_password = bool(env.get(env_key("APP_PASSWORD", suffix)) or env.get(env_key("PASSWORD", suffix)))
        if has_provider and not (has_email and has_password):
            return suffix
        if not has_provider and not has_email and not has_password:
            return suffix
    raise SystemExit("No free ZEROINBOX account slot found.")


def has_complete_account(conf: dict[str, str], env: dict[str, str]) -> bool:
    for index in range(1, 51):
        suffix = suffix_for_index(index)
        if (
            conf.get(provider_key(suffix))
            and env.get(env_key("EMAIL", suffix))
            and (env.get(env_key("APP_PASSWORD", suffix)) or env.get(env_key("PASSWORD", suffix)))
        ):
            return True
    return False


def ask_provider(default_provider: str = "") -> str:
    names = provider_names()
    options = " ".join(f"({index}) {name}" for index, name in enumerate(names, start=1))
    prompt = f"Provider key {options} or custom key, e.g. ms" if options else "Provider key"
    raw = ask(prompt, default_provider or (names[0] if names else "gmail")).strip().lower()
    if raw.isdigit():
        selected = int(raw)
        if 1 <= selected <= len(names):
            return names[selected - 1]
    if raw == "custom":
        raw = ask("Custom provider key, e.g. ms").strip().lower()
    if not raw:
        raise SystemExit("Provider required.")
    return raw


def custom_provider_updates(conf: dict[str, str], provider: str) -> dict[str, str]:
    if provider in provider_names():
        return {}
    token = provider_token(provider)
    prefix = f"ZEROINBOX_PROVIDER_{token}"
    if conf.get(f"{prefix}_URL") or conf.get(f"{prefix}_HOST"):
        return {}

    print(f"Custom provider '{provider}' needs IMAP connection values in config.conf.")
    default_host = "outlook.office365.com" if provider in {"ms", "microsoft", "outlook"} else ""
    host = ask("IMAP host or URL", default_host)
    if not host:
        raise SystemExit("IMAP host required for custom provider.")
    return {
        f"{prefix}_URL": host,
        f"{prefix}_PORT": ask("IMAP port", "993"),
        f"{prefix}_INBOX": ask("Inbox folder", "INBOX"),
        f"{prefix}_SEARCH": ask("IMAP search", "UNSEEN"),
        f"{prefix}_ARCHIVE_PREFIX": ask("Archive prefix", "ZEROINBOX/Archiv"),
        f"{prefix}_CREATE_MISSING_FOLDERS": "true",
        f"{prefix}_EXPUNGE_AFTER_MOVE": "true",
    }


def add_account() -> None:
    conf = read_kv(CONFIG_PATH)
    env = read_kv(ENV_PATH)
    suffix = first_free_or_incomplete_slot(conf, env)
    provider = ask_provider(conf.get(provider_key(suffix), ""))

    config_updates = {provider_key(suffix): provider}
    config_updates.update(custom_provider_updates(conf, provider))
    if not conf.get("ZEROINBOX_ENV_FILE"):
        config_updates["ZEROINBOX_ENV_FILE"] = ".env"
    if not conf.get("ZEROINBOX_DEFAULT_ACCOUNT"):
        config_updates["ZEROINBOX_DEFAULT_ACCOUNT"] = account_name(provider, suffix)

    email = ask("Mail address")
    if not email:
        raise SystemExit("Mail address required.")
    password = getpass.getpass("App password / IMAP password: ").strip().replace(" ", "")
    if not password:
        raise SystemExit("Password required.")

    upsert_kv(CONFIG_PATH, config_updates)
    upsert_kv(
        ENV_PATH,
        {
            env_key("EMAIL", suffix): email,
            env_key("APP_PASSWORD", suffix): password,
        },
        0o600,
    )
    print(f"Wrote {provider_key(suffix)} to {CONFIG_PATH}.")
    print(f"Wrote {env_key('EMAIL', suffix)} and {env_key('APP_PASSWORD', suffix)} to {ENV_PATH}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize ZEROINBOX accounts.")
    parser.add_argument("--new", action="store_true", help="add the next account slot")
    parser.add_argument("--skip", action="store_true", help="do nothing")
    args = parser.parse_args()

    if args.skip:
        print("ZEROINBOX account init skipped.")
        return 0

    if not args.new:
        if not sys.stdin.isatty():
            print("ZEROINBOX account init skipped: no interactive terminal.")
            return 0
        conf = read_kv(CONFIG_PATH)
        env = read_kv(ENV_PATH)
        default_mode = "skip" if has_complete_account(conf, env) else "new"
        mode = ask_choice("ZEROINBOX account init", ("skip", "new"), default_mode)
        if mode == "skip":
            print("ZEROINBOX account init skipped.")
            return 0

    add_account()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
