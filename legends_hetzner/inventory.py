# SPDX-License-Identifier: MIT
"""Read-only inventory and catalog views over `hcloud ... list -o json`."""

from __future__ import annotations

from .hcloud import Auth, HCloudError, redact_obj, require_live_auth, run_json

CATALOG_KINDS: dict[str, list[str]] = {
    "server-types": ["server-type", "list", "-o", "json"],
    "locations": ["location", "list", "-o", "json"],
    "images": ["image", "list", "-o", "json"],
    "ssh-keys": ["ssh-key", "list", "-o", "json"],
}


def _as_list(data, what: str) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("servers", "server_types", "locations", "images", "ssh_keys", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    raise HCloudError("HCLOUD_BAD_JSON", f"Unexpected {what} JSON shape: "
                      f"{type(data).__name__}; refusing false empty.")


def inventory_servers(auth: Auth, hcloud_bin: str = "hcloud",
                      timeout: int | float | None = None) -> dict:
    require_live_auth(auth)
    data = run_json(["server", "list", "-o", "json"], auth,
                    timeout=timeout, hcloud_bin=hcloud_bin)
    servers = redact_obj(_as_list(data, "server list"))
    return {"servers": servers, "count": len(servers)}


def catalog(auth: Auth, kind: str = "all", hcloud_bin: str = "hcloud",
            timeout: int | float | None = None) -> dict:
    require_live_auth(auth)
    want = (kind or "all").strip().lower()
    if want == "all":
        out: dict = {}
        for name, argv in CATALOG_KINDS.items():
            key = name.replace("-", "_")
            items = redact_obj(_as_list(
                run_json(argv, auth, timeout=timeout, hcloud_bin=hcloud_bin), f"{name} list"))
            out[key] = {"items": items, "count": len(items)}
        return out
    if want not in CATALOG_KINDS:
        raise ValueError(f"unknown catalog kind: {kind}")
    items = redact_obj(_as_list(run_json(CATALOG_KINDS[want], auth,
                                         timeout=timeout, hcloud_bin=hcloud_bin), f"{want} list"))
    return {"kind": want, "items": items, "count": len(items)}
