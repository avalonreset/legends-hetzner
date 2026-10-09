# SPDX-License-Identifier: MIT
"""Subprocess argv adapter for the external `hcloud` CLI.

Stdlib only. No shell, bounded timeouts, sanitized errors, no token
printing or persistence. Child env strips endpoint/debug overrides so an
inherited HCLOUD_ENDPOINT/HCLOUD_DEBUG cannot divert the token or log it.
Single CLI invocation per call; upstream hcloud HTTP retries (if any) are
outside this wrapper (see scope limits).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

DEFAULT_TIMEOUT = 30
MIN_TIMEOUT = 1
MAX_TIMEOUT = 120
ERROR_SNIPPET_MAX = 2000
TOKEN_ENV = "HCLOUD_TOKEN"
# Overrides stripped from the child env: custom endpoints could divert the
# token; debug flags could log it. v0.1.1 supports upstream defaults only.
STRIPPED_CHILD_ENV = ("HCLOUD_ENDPOINT", "HCLOUD_HOST", "HCLOUD_DEBUG")

# Redact only the known token value and credential-labeled values. Never a
# bare hex digest: plan_hash and user_data_sha256 must stay printable.
_AUTHORIZATION_RE = re.compile(r'(?i)(Authorization\s*:\s*(?:Bearer\s+)?)([^\s"\',}\]]+)')
_BEARER_RE = re.compile(r'(?i)(\bBearer\s+)([^\s"\',}\]]+)')
_JSON_DQ_RE = re.compile(r'(?i)("[^"]*(?:token|secret|api[_-]?key)[^"]*"\s*:\s*")([^"]*)"')
_JSON_SQ_RE = re.compile(r"(?i)('[^']*(?:token|secret|api[_-]?key)[^']*'\s*:\s*')([^']*)'")
_KV_RE = re.compile(r'(?i)([\w.\-]*?(?:token|api[_-]?key|secret)[\w.\-]*\s*[:=]\s*["\']?)([^"\'\s,}\]]+)')
_SENSITIVE_KEY_RE = re.compile(r"(?i)(token|secret|api[_-]?key|bearer|authorization)")


class HCloudError(Exception):
    """Sanitized adapter failure (no secrets)."""

    def __init__(self, code: str, message: str, exit_code: int | None = None,
                 stderr: str | None = None):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.stderr = stderr


@dataclass(frozen=True)
class Auth:
    """Single explicit auth selection for one CLI invocation."""

    context: str | None
    token_present: bool
    source: str  # "context" | "token" | "none"


def _to_str(value) -> str:
    """Decode subprocess output defensively (bytes safe, never raises)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("utf-8", errors="replace")
        except (UnicodeDecodeError, ValueError):
            return repr(bytes(value))[:500]
    try:
        return str(value)
    except (UnicodeDecodeError, ValueError):
        return "<undecodable>"


def redact_text(text: str) -> str:
    """Redact the known token and credential-labeled values only."""
    if not text:
        return "" if text is None else text
    out = _to_str(text)
    token = os.environ.get(TOKEN_ENV, "")
    if token:
        out = out.replace(token, "[REDACTED]")
    out = _AUTHORIZATION_RE.sub(r"\1[REDACTED]", out)
    out = _BEARER_RE.sub(r"\1[REDACTED]", out)
    out = _JSON_DQ_RE.sub(r"\1[REDACTED]", out)
    out = _JSON_SQ_RE.sub(r"\1[REDACTED]", out)
    return _KV_RE.sub(r"\1[REDACTED]", out)


def _redact_all(obj):
    if isinstance(obj, str):
        return "[REDACTED]"
    if isinstance(obj, list):
        return [_redact_all(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _redact_all(v) for k, v in obj.items()}
    return obj


def redact_obj(obj):
    """Recursively redact; sensitive-keyed values fully redacted."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if isinstance(key, str) and _SENSITIVE_KEY_RE.search(key):
                out[key] = _redact_all(value)
            else:
                out[key] = redact_obj(value)
        return out
    return obj


def _truncate(text: str, limit: int = ERROR_SNIPPET_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"...<truncated {len(text) - limit} chars>"


def resolve_auth(context: str | None) -> Auth:
    """Resolve explicit auth: HCLOUD_TOKEN xor --context."""
    ctx = (context or "").strip() or None
    token_present = bool((os.environ.get(TOKEN_ENV) or "").strip())
    if ctx and token_present:
        raise HCloudError(
            "AUTH_AMBIGUOUS",
            f"Set exactly one auth method: unset {TOKEN_ENV} or omit --context.",
        )
    if ctx:
        return Auth(context=ctx, token_present=False, source="context")
    if token_present:
        return Auth(context=None, token_present=True, source="token")
    return Auth(context=None, token_present=False, source="none")


def require_live_auth(auth: Auth) -> None:
    if auth.source == "none":
        raise HCloudError(
            "AUTH_MISSING",
            f"Live command needs explicit auth: set {TOKEN_ENV} or pass --context NAME.",
        )


def clamp_timeout(timeout: int | float | None) -> int:
    try:
        value = int(timeout if timeout is not None else DEFAULT_TIMEOUT)
    except (TypeError, ValueError, OverflowError):
        value = DEFAULT_TIMEOUT
    return max(MIN_TIMEOUT, min(MAX_TIMEOUT, value))


def build_argv(base_args: list[str], auth: Auth, hcloud_bin: str = "hcloud") -> list[str]:
    """Build argv list; refuses token values in args (fail closed)."""
    binary = (hcloud_bin or "").strip() or "hcloud"
    argv: list[str] = [binary]
    if auth.context:
        argv += ["--context", auth.context]
    argv += list(base_args)
    token = os.environ.get(TOKEN_ENV, "")
    if token:
        for part in argv[1:]:
            if token == part or (len(token) >= 8 and token in part):
                raise HCloudError(
                    "AUTH_LEAK_REFUSED",
                    "Refusing argv containing the API token value.",
                )
    return argv


def which_hcloud(hcloud_bin: str = "hcloud") -> str | None:
    binary = (hcloud_bin or "").strip() or "hcloud"
    if os.sep in binary or (os.altsep and os.altsep in binary):
        return binary if os.path.isfile(binary) else None
    return shutil.which(binary)


def _child_env(auth: Auth) -> dict[str, str]:
    env = dict(os.environ)
    # Enforce selected-context consistency: env token must not override --context.
    if auth.context:
        env.pop(TOKEN_ENV, None)
    for key in STRIPPED_CHILD_ENV:
        env.pop(key, None)
    return env


def run(base_args: list[str], auth: Auth, timeout: int | float | None = None,
        hcloud_bin: str = "hcloud") -> str:
    """Run one hcloud CLI invocation; no client-side retry. Returns stdout."""
    bounded = clamp_timeout(timeout)
    argv = build_argv(base_args, auth, hcloud_bin)
    label = (base_args[0] if base_args else "call").strip() or "call"
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=bounded,
            env=_child_env(auth),
        )
    except FileNotFoundError:
        raise HCloudError(
            "HCLOUD_NOT_FOUND",
            f"hcloud executable not found: {(hcloud_bin or 'hcloud').strip() or 'hcloud'}.",
        ) from None
    except subprocess.TimeoutExpired as exc:
        # Output may be bytes even with text=True; TimeoutExpired carries
        # output/stderr (older) and stdout/stderr (newer); decode defensively.
        err_raw = getattr(exc, "stderr", None)
        out_raw = getattr(exc, "stdout", None)
        if out_raw is None:
            out_raw = getattr(exc, "output", None)
        partial = _truncate(redact_text((_to_str(err_raw) + _to_str(out_raw)).strip()))
        raise HCloudError(
            "TIMEOUT",
            f"hcloud call timed out after {bounded}s: {label}.",
            stderr=partial or None,
        ) from None
    except (PermissionError, OSError) as exc:
        detail = _truncate(redact_text(_to_str(exc)))
        raise HCloudError(
            "HCLOUD_OS_ERROR",
            f"hcloud launch failed ({type(exc).__name__}): {label}.",
            stderr=detail or None,
        ) from None
    except UnicodeDecodeError as exc:
        detail = _truncate(redact_text(_to_str(exc)))
        raise HCloudError(
            "HCLOUD_DECODE_ERROR",
            f"hcloud output undecodable: {label}.",
            stderr=detail or None,
        ) from None
    stderr_s = _to_str(proc.stderr)
    stdout_s = _to_str(proc.stdout)
    if proc.returncode != 0:
        snippet = _truncate(redact_text((stderr_s or stdout_s).strip()))
        raise HCloudError(
            "HCLOUD_EXIT",
            f"hcloud exited {proc.returncode}: {label} failed.",
            exit_code=proc.returncode,
            stderr=snippet or None,
        )
    return stdout_s


def run_json(base_args: list[str], auth: Auth, timeout: int | float | None = None,
             hcloud_bin: str = "hcloud"):
    """Run one hcloud call and parse stdout as JSON."""
    out = run(base_args, auth, timeout=timeout, hcloud_bin=hcloud_bin)
    try:
        return json.loads(out) if out.strip() else None
    except json.JSONDecodeError as exc:
        snippet = _truncate(redact_text(out.strip()))
        raise HCloudError(
            "HCLOUD_BAD_JSON",
            f"hcloud returned invalid JSON: {exc.msg}.",
            stderr=snippet or None,
        ) from None
