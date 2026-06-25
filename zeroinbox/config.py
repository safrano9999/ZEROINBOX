from __future__ import annotations

import configparser
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
PROVIDER_PATH = ROOT_DIR / "provider.conf"

DEFAULT_DESTINATIONS = [
    {
        "key": "kommunikation",
        "mailbox": "{archivePrefix}/Kommunikation",
        "description": "Personal human-to-human communication, replies, appointments, direct messages.",
    },
    {
        "key": "newsletter",
        "mailbox": "{archivePrefix}/newsletter",
        "description": "Newsletters, promotions, marketing campaigns, digests, automated announcements.",
    },
    {
        "key": "systemmeldungen",
        "mailbox": "{archivePrefix}/Systemmeldungen",
        "description": "Automated provider, account, login, quota, status, API, billing or infrastructure notifications.",
    },
    {
        "key": "bezahlt",
        "mailbox": "{archivePrefix}/bezahlt",
        "description": "Invoices, receipts, payment confirmations, orders, delivery confirmations.",
    },
    {
        "key": "agb",
        "mailbox": "{archivePrefix}/AGB",
        "description": "Terms of service, privacy policy, contract or service condition changes.",
    },
    {
        "key": "welcome",
        "mailbox": "{archivePrefix}/welcome",
        "description": "Welcome mails, sign-up confirmations, onboarding sequences.",
    },
    {
        "key": "loeschen",
        "mailbox": "INBOX/loeschen",
        "description": "Obvious spam, junk, expired one-time codes, low-value automated noise.",
    },
    {
        "key": "uncertain",
        "mailbox": "INBOX/sort_ai_uncertain",
        "description": "Fallback for anything unclear or risky.",
    },
]

DEFAULT_RULES = [
    "Prefer conservative filing: if unsure, choose uncertain.",
    "Human personal messages go to kommunikation unless they are clearly automated.",
    "Marketing, newsletters, product updates and mailing-list digests go to newsletter.",
    "Security, login, provider, quota, API and system alerts go to systemmeldungen.",
    "Receipts, invoices, payment and order confirmations go to bezahlt.",
    "Terms, privacy and contract-change notices go to agb.",
    "Welcome and onboarding sequences go to welcome.",
    "Obvious junk and disposable noise can go to loeschen.",
]


def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def parse_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value if value not in {None, ""} else default


def provider_names() -> list[str]:
    providers = load_provider_conf()
    return sorted(providers)


def load_provider_conf(path: Path = PROVIDER_PATH) -> dict[str, dict[str, Any]]:
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    providers: dict[str, dict[str, Any]] = {}
    key_map = {
        "archive_prefix": "archivePrefix",
        "password_label": "passwordLabel",
        "password_env_suffix": "passwordEnvSuffix",
        "create_missing_folders": "createMissingFolders",
        "expunge_after_move": "expungeAfterMove",
    }
    for section in parser.sections():
        if not section.lower().startswith("provider."):
            continue
        name = section.split(".", 1)[1].strip().lower()
        if not name:
            continue
        values: dict[str, Any] = {}
        for raw_key, raw_value in parser.items(section):
            raw_key = raw_key.strip()
            key = key_map.get(raw_key.lower(), raw_key)
            if key == "port":
                values[key] = parse_int(raw_value, 993)
            elif key in {"createMissingFolders", "expungeAfterMove"}:
                values[key] = parse_bool(raw_value, True)
            else:
                values[key] = raw_value
        providers[name] = values
    return providers


def load_static_accounts() -> dict[str, Any]:
    return {
        "providers": load_provider_conf(),
        "destinations": DEFAULT_DESTINATIONS,
        "rules": DEFAULT_RULES,
    }


def format_destinations(static: dict[str, Any], archive_prefix: str) -> list[dict[str, str]]:
    destinations: list[dict[str, str]] = []
    for entry in static.get("destinations", []):
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        mailbox = str(entry.get("mailbox") or "").strip()
        if not key or not mailbox:
            continue
        destinations.append(
            {
                "key": key,
                "mailbox": mailbox.format(archivePrefix=archive_prefix),
                "description": str(entry.get("description") or "").strip(),
            }
        )
    return destinations


def suffix_key(base: str, suffix: str = "") -> str:
    return f"ZEROINBOX_{base}{suffix}"


def indexed_env(base: str, suffix: str = "", default: str = "") -> str:
    return env(suffix_key(base, suffix), default)


def provider_env(provider_name: str, field: str, default: str = "") -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", provider_name.upper()).strip("_")
    return env(f"ZEROINBOX_PROVIDER_{token}_{field}", default)


def parse_host_port(raw_url: str, fallback_port: int = 993) -> tuple[str, int]:
    raw = raw_url.strip()
    if not raw:
        return "", fallback_port
    parsed = urlparse(raw if "://" in raw else f"imaps://{raw}")
    host = parsed.hostname or raw.split("/", 1)[0].split(":", 1)[0]
    port = parsed.port or fallback_port
    return host, port


def account_suffixes() -> list[str]:
    suffixes: list[str] = []
    for index in range(1, 51):
        suffix = "" if index == 1 else f"_{index}"
        keys = ("PROVIDER", "EMAIL", "APP_PASSWORD", "PASSWORD")
        if any(indexed_env(key, suffix) for key in keys):
            suffixes.append(suffix)
    return suffixes or [""]


def account_name(provider_name: str, suffix: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", provider_name.lower()).strip("_") or "account"
    return normalized if not suffix else f"{normalized}{suffix}"


def indexed_password_env(suffix: str) -> str:
    if indexed_env("APP_PASSWORD", suffix) or not indexed_env("PASSWORD", suffix):
        return suffix_key("APP_PASSWORD", suffix)
    return suffix_key("PASSWORD", suffix)


def build_known_provider_account(
    static: dict[str, Any],
    suffix: str,
    provider_name: str,
    provider: dict[str, Any],
) -> dict[str, Any]:
    archive_prefix = indexed_env("ARCHIVE_PREFIX", suffix, str(provider.get("archivePrefix") or "ZEROINBOX/Archiv"))
    return {
        "name": account_name(provider_name, suffix),
        "provider": provider_name,
        "host": indexed_env("HOST", suffix, str(provider.get("host") or "")),
        "port": parse_int(indexed_env("PORT", suffix, str(provider.get("port") or 993)), 993),
        "usernameEnv": suffix_key("EMAIL", suffix),
        "passwordEnv": indexed_password_env(suffix),
        "inbox": indexed_env("INBOX", suffix, str(provider.get("inbox") or "INBOX")),
        "search": indexed_env("SEARCH", suffix, str(provider.get("search") or "UNSEEN")),
        "createMissingFolders": parse_bool(
            indexed_env("CREATE_MISSING_FOLDERS", suffix, str(provider.get("createMissingFolders", True))),
            True,
        ),
        "expungeAfterMove": parse_bool(
            indexed_env("EXPUNGE_AFTER_MOVE", suffix, str(provider.get("expungeAfterMove", True))),
            True,
        ),
        "destinations": format_destinations(static, archive_prefix),
    }


def build_dynamic_provider_account(static: dict[str, Any], suffix: str, provider_name: str) -> dict[str, Any]:
    provider_url = provider_env(provider_name, "URL") or provider_env(provider_name, "HOST")
    fallback_port = parse_int(provider_env(provider_name, "PORT", "993"), 993)
    host, parsed_port = parse_host_port(provider_url, fallback_port)
    port = parse_int(indexed_env("PORT", suffix, str(parsed_port)), parsed_port)
    if not host:
        token = re.sub(r"[^A-Za-z0-9]+", "_", provider_name.upper()).strip("_")
        raise ValueError(
            f"Provider '{provider_name}' is not in provider.conf. "
            f"Set ZEROINBOX_PROVIDER_{token}_URL and optionally ZEROINBOX_PROVIDER_{token}_PORT."
        )
    archive_prefix = indexed_env(
        "ARCHIVE_PREFIX",
        suffix,
        provider_env(provider_name, "ARCHIVE_PREFIX", "ZEROINBOX/Archiv"),
    )
    return {
        "name": account_name(provider_name, suffix),
        "provider": provider_name,
        "host": host,
        "port": port,
        "usernameEnv": suffix_key("EMAIL", suffix),
        "passwordEnv": indexed_password_env(suffix),
        "inbox": indexed_env("INBOX", suffix, provider_env(provider_name, "INBOX", "INBOX")),
        "search": indexed_env("SEARCH", suffix, provider_env(provider_name, "SEARCH", "UNSEEN")),
        "createMissingFolders": parse_bool(
            indexed_env("CREATE_MISSING_FOLDERS", suffix, provider_env(provider_name, "CREATE_MISSING_FOLDERS", "true")),
            True,
        ),
        "expungeAfterMove": parse_bool(
            indexed_env("EXPUNGE_AFTER_MOVE", suffix, provider_env(provider_name, "EXPUNGE_AFTER_MOVE", "true")),
            True,
        ),
        "destinations": format_destinations(static, archive_prefix),
    }


def build_accounts(static: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers = static.get("providers") if isinstance(static.get("providers"), dict) else {}
    accounts: dict[str, dict[str, Any]] = {}
    for suffix in account_suffixes():
        provider_name = indexed_env("PROVIDER", suffix, "gmail" if not suffix else "").strip().lower()
        if not provider_name:
            continue
        if provider_name in providers:
            account = build_known_provider_account(static, suffix, provider_name, providers[provider_name])
        else:
            account = build_dynamic_provider_account(static, suffix, provider_name)
        accounts[account["name"]] = account
    return accounts


def load_config(report_dir: Path | None = None) -> dict[str, Any]:
    static = load_static_accounts()
    accounts = build_accounts(static)
    default_account = next(iter(accounts), "")

    return {
        "defaultAccount": default_account,
        "defaultModel": env("ZEROINBOX_MODEL", "gemini/gemini-flash-lite-latest"),
        "classifier": "openai_v1",
        "accounts": accounts,
        "rules": static.get("rules") if isinstance(static.get("rules"), list) else [],
        "_baseDir": str(ROOT_DIR),
        "_reportDir": str(report_dir) if report_dir else "",
    }


def account_config(config: dict[str, Any], account: str | None = None) -> dict[str, Any]:
    account_name = (account or str(config.get("defaultAccount") or "")).lower()
    accounts = config.get("accounts")
    if not isinstance(accounts, dict) or account_name not in accounts:
        available = ", ".join(sorted(accounts)) if isinstance(accounts, dict) else "<none>"
        raise ValueError(f"Unknown account '{account_name}'. Available: {available}")
    selected = dict(accounts[account_name])
    selected["name"] = account_name
    return selected


def account_names(config: dict[str, Any], account: str | None = None) -> list[str]:
    if account:
        account_config(config, account)
        return [account.lower()]
    accounts = config.get("accounts")
    if not isinstance(accounts, dict):
        return []
    names = list(accounts)
    default = str(config.get("defaultAccount") or "").strip().lower()
    if default in names:
        names.remove(default)
        names.insert(0, default)
    return names


def mailbox_accounts(config: dict[str, Any], account: str | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in account_names(config, account):
        base = account_config(config, name)
        entries = base.get("mailboxes") or base.get("inboxes")
        if not isinstance(entries, list) or not entries:
            item = dict(base)
            item.pop("mailboxes", None)
            item.pop("inboxes", None)
            item["mailboxLabel"] = str(item.get("inbox") or "INBOX")
            result.append(item)
            continue
        for entry in entries:
            item = dict(base)
            item.pop("mailboxes", None)
            item.pop("inboxes", None)
            if isinstance(entry, dict):
                inbox = str(entry.get("inbox") or entry.get("mailbox") or entry.get("name") or "").strip()
                if not inbox:
                    continue
                item["inbox"] = inbox
                item["search"] = str(entry.get("search") or item.get("search") or "UNSEEN")
                item["mailboxLabel"] = str(entry.get("label") or entry.get("name") or inbox)
            else:
                inbox = str(entry or "").strip()
                if not inbox:
                    continue
                item["inbox"] = inbox
                item["mailboxLabel"] = inbox
            result.append(item)
    return result


def resolve_secret(account: dict[str, Any], key: str) -> str:
    direct = account.get(key)
    if isinstance(direct, str) and direct:
        return direct
    env_name = account.get(f"{key}Env")
    if isinstance(env_name, str) and env_name:
        value = os.environ.get(env_name, "")
        if value:
            return value
    return ""


def resolve_model(config: dict[str, Any]) -> str:
    return os.environ.get("ZEROINBOX_MODEL") or str(config.get("defaultModel") or "gpt-4o-mini")


def log_dir(config: dict[str, Any]) -> Path:
    return Path(str(config["_baseDir"])) / "logs"
