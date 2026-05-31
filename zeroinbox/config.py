from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
            os.environ.setdefault(key, value)
    return values


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    config["_configPath"] = str(path)
    config["_baseDir"] = str(path.parent)
    env_file = config.get("envFile")
    if isinstance(env_file, str) and env_file.strip():
        env_path = Path(env_file).expanduser()
        if not env_path.is_absolute():
            env_path = path.parent / env_path
        load_dotenv(env_path)
        config["_envPath"] = str(env_path)
    return config


def read_env_name(config: dict[str, Any], name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    return str(config.get(name, default) or default)


def account_config(config: dict[str, Any], account: str | None = None) -> dict[str, Any]:
    account_name = account or str(config.get("defaultAccount") or "")
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
        return [account]
    accounts = config.get("accounts")
    if not isinstance(accounts, dict):
        return []
    names = list(accounts)
    default = str(config.get("defaultAccount") or "").strip()
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
        return os.environ.get(env_name, "")
    return ""


def resolve_model(config: dict[str, Any]) -> str:
    return (
        os.environ.get("ZEROINBOX_MODEL")
        or str(config.get("defaultModel") or "gpt-4o-mini")
    )


def log_dir(config: dict[str, Any]) -> Path:
    raw = str(config.get("logDir") or "logs")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(str(config["_baseDir"])) / path
    return path
