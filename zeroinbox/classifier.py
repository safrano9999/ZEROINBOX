from __future__ import annotations

import json
from typing import Any

from .config import resolve_model
from .models import Decision, Destination, MailSummary
from openai_v1_stream import openai_v1_stream_buffer
from python_header import openai_v1_client, openai_v1_first_provider, openai_v1_provider_for_model

_DECISION_KEYS = {"destination", "confidence", "summary", "reason"}


def destination_list(account: dict[str, Any]) -> list[Destination]:
    values = account.get("destinations")
    if not isinstance(values, list):
        raise ValueError("Account config must define destinations.")
    destinations: list[Destination] = []
    for entry in values:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        mailbox = str(entry.get("mailbox") or "").strip()
        if key and mailbox:
            destinations.append(
                Destination(
                    key=key,
                    mailbox=mailbox,
                    description=str(entry.get("description") or "").strip(),
                )
            )
    if not destinations:
        raise ValueError("Account config has no usable destinations.")
    return destinations


def destination_map(account: dict[str, Any]) -> dict[str, Destination]:
    return {item.key: item for item in destination_list(account)}


def build_prompt(config: dict[str, Any], account: dict[str, Any], mail: MailSummary) -> str:
    rules = config.get("rules")
    rule_text = "\n".join(f"- {item}" for item in rules if isinstance(item, str)) if isinstance(rules, list) else ""
    destinations = destination_list(account)
    dest_text = "\n".join(
        f"- {item.key}: {item.description} -> {item.mailbox}" for item in destinations
    )
    allowed = ", ".join(item.key for item in destinations)
    return f"""You are ZEROINBOX, a conservative email sorting agent.

Return strict JSON only with these keys:
destination, confidence, summary, reason

destination must be exactly one of: {allowed}
confidence must be a number between 0 and 1.

Rules:
{rule_text}

Destinations:
{dest_text}

Email:
From: {mail.sender}
Date: {mail.date}
Subject: {mail.subject}

Body snippet:
{mail.body[:4000]}
"""


def parse_json_object(raw: str | bytes | bytearray) -> dict[str, Any]:
    text = raw.strip()
    opening = "{" if isinstance(text, str) else b"{"
    closing = "}" if isinstance(text, str) else b"}"
    if not text.startswith(opening) or not text.endswith(closing):
        raise ValueError("Classifier response is not a strict JSON object.")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError("Classifier response contains a duplicate field.")
            payload[key] = value
        return payload

    payload = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    if not isinstance(payload, dict):
        raise ValueError("Classifier response is not a JSON object.")
    keys = set(payload)
    if keys != _DECISION_KEYS:
        raise ValueError("Classifier response has unexpected or missing fields.")
    if not isinstance(payload["destination"], str):
        raise ValueError("Classifier destination must be a string.")
    if isinstance(payload["confidence"], bool) or not isinstance(payload["confidence"], (int, float)):
        raise ValueError("Classifier confidence must be a number.")
    if not isinstance(payload["summary"], str) or not isinstance(payload["reason"], str):
        raise ValueError("Classifier summary and reason must be strings.")
    return payload


def normalize_decision(payload: dict[str, Any], account: dict[str, Any]) -> Decision:
    destinations = destination_map(account)
    destination = str(payload.get("destination") or "uncertain").strip().lower()
    if destination not in destinations:
        destination = "uncertain" if "uncertain" in destinations else next(iter(destinations))
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return Decision(
        destination=destination,
        confidence=confidence,
        summary=str(payload.get("summary") or "").strip()[:500],
        reason=str(payload.get("reason") or "").strip()[:1000],
    )


def openai_v1_model(config: dict[str, Any]) -> str:
    return resolve_model(config)


def openai_v1_configured() -> bool:
    return openai_v1_first_provider() is not None


def ensure_classifier_ready(config: dict[str, Any], classifier: str | None = None) -> None:
    mode = (classifier or str(config.get("classifier") or "openai_v1")).strip().lower()
    if mode == "rules" or openai_v1_configured():
        return
    raise RuntimeError(
        "OpenAI v1 endpoint is missing. Set OPENAI_V1_URL, OPENAI_V1_PORT, OPENAI_V1_KEY, "
        "or run with --classifier rules for a non-LLM mechanics test."
    )


def classify_openai_v1(config: dict[str, Any], account: dict[str, Any], mail: MailSummary) -> Decision:
    ensure_classifier_ready(config, "openai_v1")
    model = openai_v1_model(config)
    provider = openai_v1_provider_for_model(model)
    if provider is None:
        raise RuntimeError("OPENAI_V1_URL is not configured.")

    response = openai_v1_client(provider, timeout=120.0).chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": build_prompt(config, account, mail)}],
        temperature=0,
        stream=provider.stream,
    )
    if provider.stream:
        with openai_v1_stream_buffer(response) as raw_buffer:
            if not raw_buffer:
                raise ValueError("Classifier returned no JSON content.")
            payload = parse_json_object(raw_buffer)
        return normalize_decision(payload, account)
    else:
        content = response.choices[0].message.content
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        raw = (content or "").strip()

    if not raw:
        raise ValueError("Classifier returned no JSON content.")
    try:
        payload = parse_json_object(raw)
    finally:
        raw = ""
    return normalize_decision(payload, account)


def classify_rules(account: dict[str, Any], mail: MailSummary) -> Decision:
    text = f"{mail.sender}\n{mail.subject}\n{mail.body}".lower()
    checks = [
        ("bezahlt", ["invoice", "rechnung", "receipt", "payment", "paid", "order", "bestellung"]),
        ("agb", ["terms", "privacy", "datenschutz", "bedingungen", "policy", "vertrag"]),
        ("systemmeldungen", ["security", "login", "alert", "quota", "api", "status", "password", "2fa"]),
        ("welcome", ["welcome", "willkommen", "getting started", "confirm your email"]),
        ("newsletter", ["unsubscribe", "newsletter", "angebot", "sale", "digest", "campaign"]),
        ("loeschen", ["spam", "lottery", "winner", "crypto giveaway"]),
    ]
    destinations = destination_map(account)
    for key, words in checks:
        if key in destinations and any(word in text for word in words):
            return Decision(key, 0.62, f"Rule match for {key}.", "Matched built-in keyword classifier.")
    fallback = "uncertain" if "uncertain" in destinations else next(iter(destinations))
    return Decision(fallback, 0.3, "No strong rule match.", "Conservative fallback.")


def classify(config: dict[str, Any], account: dict[str, Any], mail: MailSummary, classifier: str | None = None) -> Decision:
    mode = (classifier or str(config.get("classifier") or "openai_v1")).strip().lower()
    if mode == "rules":
        return classify_rules(account, mail)
    return classify_openai_v1(config, account, mail)
