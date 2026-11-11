# SPDX-License-Identifier: MIT
"""Subprocess argv adapter for the external `hcloud` CLI.

Stdlib only. No shell, bounded timeouts, sanitized errors, no token
printing or persistence. Child env strips endpoint/debug overrides so an
inherited HCLOUD_ENDPOINT/HCLOUD_DEBUG cannot divert the token or log it.
Single CLI invocation per call; upstream hcloud HTTP retries (if any) are
outside this wrapper (see scope limits).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
import urllib.error
import urllib.request

from . import __version__

_REAL_SUBPROCESS_RUN = subprocess.run
HETZNER_SERVER_TYPES_URL = "https://api.hetzner.cloud/v1/server_types"
_MAX_REST_BYTES = 2 * 1024 * 1024
_KNOWN_CONTEXT_TOKENS: set[str] = set()
_CONTEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

DEFAULT_TIMEOUT = 30
MIN_TIMEOUT = 1
MAX_TIMEOUT = 120
ERROR_SNIPPET_MAX = 2000
TOKEN_ENV = "HCLOUD_TOKEN"
# Overrides stripped from the child env: custom endpoints could divert the
# token; debug flags could log it. v0.1.3 supports upstream defaults only.
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
    for ctx_token in tuple(_KNOWN_CONTEXT_TOKENS):
        if ctx_token:
            out = out.replace(ctx_token, "[REDACTED]")
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
    if ctx is not None and not _CONTEXT_RE.match(ctx):
        raise HCloudError(
            "AUTH_INVALID_CONTEXT",
            "Invalid --context name; use 1..64 alphanumeric/._- chars without leading '-'.",
        )
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
        if not _CONTEXT_RE.match(auth.context):
            raise HCloudError(
                "AUTH_INVALID_CONTEXT",
                "Invalid --context name; use 1..64 alphanumeric/._- chars without leading '-'.",
            )
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


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject all HTTP redirects fail-closed so Bearer credentials never redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"HTTP redirects are refused ({code})",
            headers,
            fp,
        )


def _default_rest_opener():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )


def _resolve_rest_token(auth: Auth) -> str | None:
    """Resolve the active token for read-only REST server_types enrichment.

    Never reads third-party CLI credential stores (%APPDATA%/hcloud/cli.toml
    or ~/.config/hcloud/cli.toml) in Python per Windows 11 EDR Gate Law 3.
    Only uses HCLOUD_TOKEN from os.environ when auth.source == 'token'.
    """
    if auth.source == "token":
        tok = (os.environ.get(TOKEN_ENV) or "").strip()
        return tok or None
    return None


def _server_types_need_enrichment(items: list) -> bool:
    """Return True when hcloud (such as 1.61.0) omitted category or available."""
    if not isinstance(items, list) or not items:
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        if not item.get("category"):
            return True
        locs = item.get("locations")
        if isinstance(locs, list):
            for loc in locs:
                if isinstance(loc, dict) and "available" not in loc:
                    return True
    return False


def enrich_server_types_via_rest(
    items: list,
    auth: Auth,
    timeout: int | float | None = None,
    opener=None,
) -> tuple[list, bool]:
    """Enrich server-type list with category/available from official REST API.

    Used when an older hcloud binary (such as 1.61.0) strips locations[].available
    and category from `hcloud server-type list -o json`. Read-only, stdlib only,
    official endpoint only. Fails open to the original CLI list if unreachable.
    """
    if not _server_types_need_enrichment(items):
        return items, False
    token = _resolve_rest_token(auth)
    if not token:
        return items, False
    bounded = clamp_timeout(timeout)
    if opener is not None:
        open_fn = opener
    else:
        open_fn = _default_rest_opener().open
    rest_by_name: dict[str, dict] = {}
    rest_by_id: dict[int, dict] = {}
    page = 1
    try:
        while page <= 5:
            url = f"{HETZNER_SERVER_TYPES_URL}?per_page=50&page={page}"
            if not url.startswith("https://api.hetzner.cloud/v1/server_types"):
                raise ValueError("Refusing non-official Hetzner REST endpoint")
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "User-Agent": f"legends-hetzner/{__version__}",
                },
                method="GET",
            )
            with open_fn(req, timeout=bounded) as resp:
                raw = resp.read(_MAX_REST_BYTES + 1)
            if len(raw) > _MAX_REST_BYTES:
                raise ValueError("REST response exceeds _MAX_REST_BYTES limit")
            payload = json.loads(_to_str(raw))
            if not isinstance(payload, dict):
                break
            st_list = payload.get("server_types")
            if not isinstance(st_list, list):
                break
            for st in st_list:
                if not isinstance(st, dict):
                    continue
                name = str(st.get("name") or "").strip().lower()
                if name:
                    rest_by_name[name] = st
                st_id = st.get("id")
                if isinstance(st_id, int) and not isinstance(st_id, bool):
                    rest_by_id[st_id] = st
            meta = payload.get("meta")
            pagination = meta.get("pagination") if isinstance(meta, dict) else None
            next_page = pagination.get("next_page") if isinstance(pagination, dict) else None
            if not isinstance(next_page, int) or isinstance(next_page, bool) or next_page <= page:
                break
            page = next_page
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        http.client.HTTPException,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return items, False

    if not rest_by_name and not rest_by_id:
        return items, False

    enriched_any = False
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        item_name = str(item.get("name") or "").strip().lower()
        rest_st = (
            rest_by_id.get(item_id)
            if isinstance(item_id, int) and not isinstance(item_id, bool)
            else None
        ) or rest_by_name.get(item_name)
        if not isinstance(rest_st, dict):
            continue
        if not item.get("category") and rest_st.get("category"):
            item["category"] = rest_st["category"]
            enriched_any = True
        if not item.get("prices") and isinstance(rest_st.get("prices"), list):
            item["prices"] = rest_st["prices"]
            enriched_any = True
        rest_locs = rest_st.get("locations")
        if not isinstance(rest_locs, list):
            continue
        rest_loc_by_name = {
            str(rl.get("name") or "").strip().lower(): rl
            for rl in rest_locs
            if isinstance(rl, dict) and rl.get("name")
        }
        rest_loc_by_id = {
            rl["id"]: rl
            for rl in rest_locs
            if isinstance(rl, dict)
            and isinstance(rl.get("id"), int)
            and not isinstance(rl.get("id"), bool)
        }
        locs = item.get("locations")
        if isinstance(locs, list):
            for loc in locs:
                if not isinstance(loc, dict):
                    continue
                loc_id = loc.get("id")
                loc_name = str(loc.get("name") or "").strip().lower()
                rl = (
                    rest_loc_by_id.get(loc_id)
                    if isinstance(loc_id, int) and not isinstance(loc_id, bool)
                    else None
                ) or rest_loc_by_name.get(loc_name)
                if not isinstance(rl, dict):
                    continue
                if "available" not in loc and "available" in rl:
                    loc["available"] = rl["available"]
                    enriched_any = True
                if "recommended" not in loc and "recommended" in rl:
                    loc["recommended"] = rl["recommended"]
                    enriched_any = True
    return items, enriched_any


def run_json(base_args: list[str], auth: Auth, timeout: int | float | None = None,
             hcloud_bin: str = "hcloud"):
    """Run one hcloud call and parse stdout as JSON."""
    out = run(base_args, auth, timeout=timeout, hcloud_bin=hcloud_bin)
    try:
        parsed = json.loads(out) if out.strip() else None
    except json.JSONDecodeError as exc:
        snippet = _truncate(redact_text(out.strip()))
        raise HCloudError(
            "HCLOUD_BAD_JSON",
            f"hcloud returned invalid JSON: {exc.msg}.",
            stderr=snippet or None,
        ) from None
    if (
        isinstance(parsed, list)
        and list(base_args)[:2] == ["server-type", "list"]
        and subprocess.run is _REAL_SUBPROCESS_RUN
    ):
        parsed, _ = enrich_server_types_via_rest(parsed, auth, timeout=timeout)
    return parsed
