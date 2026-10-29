# SPDX-License-Identifier: MIT
"""Offline-first health checks plus an opt-in live probe."""

from __future__ import annotations

import sys

from . import PROVISION_SUPPORT, TOOL, __version__
from .hcloud import (
    Auth,
    HCloudError,
    clamp_timeout,
    require_live_auth,
    run,
    run_json,
    which_hcloud,
)


def offline(hcloud_bin: str = "hcloud", timeout: int | float | None = None) -> dict:
    """Offline checks: interpreter, binary presence, hcloud version."""
    bounded = clamp_timeout(timeout if timeout is not None else 10)
    found = which_hcloud(hcloud_bin)
    version: str | None = None
    errors: list[dict] = []
    if found is None:
        errors.append({"code": "HCLOUD_NOT_FOUND", "message": "hcloud executable not found."})
    else:
        try:
            out = run(["version"], Auth(context=None, token_present=False, source="none"),
                      timeout=bounded, hcloud_bin=hcloud_bin)
            version = (out or "").strip().splitlines()[0][:200] if out.strip() else "ok"
        except HCloudError as exc:
            errors.append({"code": exc.code, "message": str(exc)})
    return {
        "tool": TOOL,
        "version": __version__,
        "mode": "offline",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_ok": sys.version_info >= (3, 11),
        "hcloud_bin": (hcloud_bin or "hcloud").strip() or "hcloud",
        "hcloud_found": found is not None,
        "hcloud_version": version,
        "provision_support": PROVISION_SUPPORT,
        "errors": errors,
    }


def live(auth: Auth, hcloud_bin: str = "hcloud",
         timeout: int | float | None = None) -> dict:
    """Live read-only probe on top of offline checks."""
    report = offline(hcloud_bin=hcloud_bin, timeout=timeout)
    report["mode"] = "live"
    report["auth_source"] = auth.source
    if auth.context:
        report["auth_context"] = auth.context
    try:
        require_live_auth(auth)
    except HCloudError as exc:
        report.setdefault("errors", []).append({"code": exc.code, "message": str(exc)})
        report["live_ok"] = False
        return report
    try:
        data = run_json(["location", "list", "-o", "json"], auth,
                        timeout=timeout, hcloud_bin=hcloud_bin)
        if not isinstance(data, list):
            report.setdefault("errors", []).append({
                "code": "HCLOUD_BAD_JSON",
                "message": f"Unexpected location list shape: {type(data).__name__}.",
            })
            report["live_ok"] = False
            return report
        report["live_ok"] = True
        report["probe"] = {"command": "location list", "count": len(data)}
    except HCloudError as exc:
        entry: dict = {"code": exc.code, "message": str(exc)}
        if exc.stderr:
            entry["detail"] = exc.stderr
        report.setdefault("errors", []).append(entry)
        report["live_ok"] = False
    return report
