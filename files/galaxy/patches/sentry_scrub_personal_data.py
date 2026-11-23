"""Remove personal data from Sentry events before they leave the server."""

import ipaddress
import re
from collections.abc import (
    Callable,
    Collection,
)
from typing import Any

EMAIL_PLACEHOLDER = "[email]"
IP_PLACEHOLDER = "[ip]"
FILTERED = "[Filtered]"

# Each part is bounded, so long strings without an address are scanned in linear time.
# The local part allows the characters used in practice, not all those RFC 5322 allows,
# so URLs and paths before an address are left alone.
# The last domain label must start with a letter, which leaves "samtools@1.21" alone.
_EMAIL_RE = re.compile(r"(?<![\w.%+-])\w[\w.%+'-]{0,63}(?:@|%40)(?:[\w-]{1,63}\.){1,8}[^\W\d_][\w-]{0,62}(?![\w-])")
_IPV4_RE = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?!\.?\d)")
_IPV6_RE = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9A-Fa-f]{0,4})(?![\w:])")
# A secret name is a whole word or its last "_" or "-" separated part, such as "key",
# "api_key", "access_token" or "galaxysession", so "dbkey" and "max_tokens" are kept.
_SECRET_NAME = (
    r"(?:[A-Za-z0-9]{1,40}[_-]){0,3}"
    r"(?:api[_-]?key|key|token|session(?:[_-]?id)?|password|passwd|secret|authorization|galaxysession\w{0,20})"
)
# name=value, as in URLs and Cookie headers.
# Also after an encoded "/", "&" or "?", as in a URL passed as a parameter.
_SECRET_ASSIGN_RE = re.compile(
    rf"(?:(?<![\w-])|(?<=%2F)|(?<=%26)|(?<=%3F))({_SECRET_NAME}(?:=|%3D))[^&;,\s'\"%]+", re.IGNORECASE
)
# 'name': 'value' and "name": "value", as in JSON and Python reprs.
_SECRET_QUOTED_RE = re.compile(rf"([\"']{_SECRET_NAME}[\"']\s*:\s*[\"'])[^\"']+", re.IGNORECASE)
# Header lines and bearer tokens.
_SECRET_HEADER_RE = re.compile(r"(\b(?:proxy-)?authorization\s*:\s*|\bx-api-key\s*:\s*)[^\r\n,;'\"]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(\bbearer\s+)[\w.~+/=-]+", re.IGNORECASE)

# Request headers that carry credentials or the client's address.
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "forwarded",
    "proxy-authorization",
    "remote-addr",
    "remote-user",
    "x-api-key",
    "x-client-ip",
    "x-forwarded-for",
    "x-real-ip",
}


def _is_address(candidate: str) -> bool:
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return True
        # Leaves strings such as "a::b" alone, which parse as reserved addresses.
        return not (address.is_reserved or address.is_unspecified or address.is_loopback)
    return True


def _replace_ip(match: re.Match[str]) -> str:
    candidate: str = match.group(0)
    return IP_PLACEHOLDER if _is_address(candidate) else candidate


def scrub_string(value: str) -> str:
    """Mask e-mail addresses, IP addresses, API keys, tokens and session cookies in a string."""
    if "@" in value or "%40" in value:
        value = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, value)
    value = _SECRET_ASSIGN_RE.sub(rf"\g<1>{FILTERED}", value)
    value = _SECRET_QUOTED_RE.sub(rf"\g<1>{FILTERED}", value)
    value = _SECRET_HEADER_RE.sub(rf"\g<1>{FILTERED}", value)
    value = _BEARER_RE.sub(rf"\g<1>{FILTERED}", value)
    if ":" in value:
        value = _IPV6_RE.sub(_replace_ip, value)
    if "." in value:
        value = _IPV4_RE.sub(_replace_ip, value)
    return value


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_string(value)
    if isinstance(value, dict):
        return {_scrub(key): _scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value


def _scrub_request(request: dict[str, Any]) -> None:
    for key in ("cookies", "data", "env"):
        request.pop(key, None)
    headers = request.get("headers")
    if isinstance(headers, dict):
        for name in list(headers):
            if name.lower() in _SENSITIVE_HEADERS:
                headers[name] = FILTERED


# Tags holding tool ids and versions; four-part versions would otherwise look like IPv4 addresses.
_TOOL_TAGS = frozenset(("tool", "tool_id", "tool_version", "tool.version"))


def _drop_log_parameters(event: dict[str, Any]) -> None:
    # Values passed to a log call cannot be recognised in general; keep the template only.
    logentry = event.get("logentry")
    if isinstance(logentry, dict) and logentry.get("params"):
        logentry.pop("params")
        logentry.pop("formatted", None)
    attributes = event.get("attributes")
    if isinstance(attributes, dict):
        template = attributes.get("sentry.message.template")
        if template is not None:
            event["body"] = template.get("value") if isinstance(template, dict) else template
            for name in [name for name in attributes if name.startswith("sentry.message.parameter.")]:
                del attributes[name]


def scrub_event(event: dict[str, Any]) -> dict[str, Any]:
    """Remove user details and personal data from a Sentry event.

    Drops the user block, cookies, request bodies, the client address, Celery task
    arguments and the values passed to log calls, and masks e-mail addresses, IP addresses, API keys, tokens and
    session cookies in every string of the event, dictionary keys included. The
    event's top-level values are replaced, and the event is returned.
    """
    event.pop("user", None)
    request = event.get("request")
    if isinstance(request, dict):
        _scrub_request(request)
    extra = event.get("extra")
    celery_job = extra.get("celery-job") if isinstance(extra, dict) else None
    if isinstance(celery_job, dict):
        for key in ("args", "kwargs"):
            if key in celery_job:
                celery_job[key] = FILTERED
    _drop_log_parameters(event)
    tags = event.get("tags")
    kept_tags = {name: tags[name] for name in _TOOL_TAGS if name in tags} if isinstance(tags, dict) else {}
    for key in list(event):
        event[key] = _scrub(event[key])
    if kept_tags:
        event["tags"].update(kept_tags)
    return event


def scrub_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any] | None) -> dict[str, Any]:
    """Scrub a breadcrumb, keeping only the template of a log message that has arguments."""
    record = (hint or {}).get("log_record")
    if record is not None and record.args:
        crumb["message"] = str(record.msg)
    scrubbed: dict[str, Any] = _scrub(crumb)
    return scrubbed


# Options of sentry-sdk 3 that collect personal data by default.
_DATA_COLLECTION_OFF: dict[str, Any] = {
    "user_info": False,
    "cookies": {"mode": "off"},
    "http_bodies": [],
    "url_query_params": {"mode": "off"},
    "graphql": {"document": False, "variables": False},
    "gen_ai": {"inputs": False, "outputs": False},
    "mcp": {"inputs": False, "outputs": False},
    "database_query_data": False,
    "queues": False,
    "stack_frame_variables": False,
}

# Hooks for items that do not pass through before_send: transactions (sentry-sdk 2),
# spans, logs and metrics (sentry-sdk 3).
_EXTRA_HOOKS = ("before_send_transaction", "before_send_span", "before_send_log", "before_send_metric")


def scrub_options(supported: Collection[str], hook: Callable[[Any, Any], Any]) -> dict[str, Any]:
    """Options for ``sentry_sdk.init`` that stop the SDK from collecting personal data.

    ``supported`` holds the option names the installed sentry-sdk accepts. ``hook``
    is registered for every item type that skips ``before_send``. Stack frame
    variables are turned off, as request objects, user objects and user ids in
    them cannot be recognised reliably.
    """
    options: dict[str, Any] = {name: hook for name in _EXTRA_HOOKS if name in supported}
    options["before_breadcrumb"] = scrub_breadcrumb
    if "data_collection" in supported:
        options["data_collection"] = dict(_DATA_COLLECTION_OFF)
    else:
        options["send_default_pii"] = False
        options["include_local_variables"] = False
    return options
