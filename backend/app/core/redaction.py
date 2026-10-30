"""
Secret redaction for anything that is persisted or returned to a client: check output, deployment logs,
error messages, workflow events.

Two layers:
* every secret the process itself knows (provider token, LLM key, JWT secret, database password) is replaced
  literally - this also catches secrets that do not look like a recognisable token;
* well-known credential shapes (GitHub/GitLab tokens, bearer headers, URL userinfo, private-key blocks) are
  replaced by pattern, because repository code run during QA can print credentials this process never held.
"""
from __future__ import annotations

import base64
import re

from app.core.config import get_settings

_MIN_SECRET_LEN = 6   # never "redact" tiny values such as "x": it would shred ordinary text
_PLACEHOLDER_SECRETS = {"change-me", "change-me-in-production", "change-me-to-a-long-random-string", "agent_password"}

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED TOKEN]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{12,}\b"), "[REDACTED TOKEN]"),
    (re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test)?[-_]?[A-Za-z0-9]{24,}\b"), "[REDACTED KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED AWS KEY ID]"),
    (re.compile(r"(?i)\b(authorization\s*[:=]\s*(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=\-]{8,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]{16,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b((?:api[_-]?key|secret|token|password|passwd)\s*[=:]\s*)(['\"]?)[^\s'\"]{8,}\2"), r"\1[REDACTED]"),
    (re.compile(r"(https?://)[^/@\s:]+(?::[^/@\s]*)?@"), r"\1[REDACTED]@"),
]


def _known_secrets() -> list[str]:
    s = get_settings()
    values = [s.GIT_PROVIDER_TOKEN, s.MISTRAL_API_KEY, s.AUTH_JWT_SECRET, s.POSTGRES_PASSWORD]
    out: list[str] = []
    for v in values:
        if v and len(v) >= _MIN_SECRET_LEN and v not in _PLACEHOLDER_SECRETS:
            out.append(v)
            if v == s.GIT_PROVIDER_TOKEN:   # the push helper sends it base64 encoded inside a header
                out.append(base64.b64encode(f"x-access-token:{v}".encode()).decode())
    return sorted(set(out), key=len, reverse=True)


def redact(text: str | None) -> str:
    """Return `text` with known secrets and credential-shaped strings replaced. Safe on None/empty."""
    if not text:
        return text or ""
    for secret in _known_secrets():
        text = text.replace(secret, "[REDACTED]")
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text
