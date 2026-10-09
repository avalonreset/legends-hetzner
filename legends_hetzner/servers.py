# SPDX-License-Identifier: MIT
"""Immutable server plan files, live preflight, single-invocation create.

Uses location (datacenter is deprecated in hcloud 1.61.0). Create performs
one CLI invocation with no client-side retry; upstream hcloud HTTP retries
(if any) are outside this wrapper. Timeouts and ambiguous results are
reported as uncertain_* via readback, never as false success or false
no-resource.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import PROVISION_SUPPORT, TOOL, __version__
from .hcloud import Auth, HCloudError, redact_obj, redact_text, require_live_auth, run, run_json

PLAN_VERSION = 1
PLAN_HASH_PREFIX = "sha256:"
DEFAULT_MAX_AGE_HOURS = 24
MAX_USERDATA_BYTES = 32768

_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,61}[A-Za-z0-9])?$")
_HASH_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


class PlanError(HCloudError):
    pass


class PreflightBlocked(HCloudError):
    def __init__(self, message: str, checks: list[dict]):
        super().__init__("PREFLIGHT_BLOCKED", message)
        self.checks = checks


class CreateError(HCloudError):
    pass


class UncertainError(HCloudError):
    def __init__(self, code: str, message: str, readback: dict | None = None):
        super().__init__(code, message)
        self.readback = readback or {}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_hash_of(payload: dict) -> str:
    return PLAN_HASH_PREFIX + _sha_hex(canonical_json(payload).encode("utf-8"))


def validate_name(name: str) -> str:
    value = (name or "").strip()
    if not value or not _NAME_RE.match(value):
        raise PlanError("PLAN_INVALID", f"Invalid server name: {value!r}.")
    return value


def validate_user_data(data: bytes) -> str:
    if len(data) > MAX_USERDATA_BYTES:
        raise PlanError("USERDATA_INVALID",
                        f"user-data exceeds {MAX_USERDATA_BYTES} bytes.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise PlanError("USERDATA_INVALID", "user-data must be UTF-8 text.") from None
    stripped = text.lstrip()
    if not stripped.startswith("#cloud-config") and not stripped.startswith("#!/"):
        raise PlanError("USERDATA_INVALID",
                        "user-data must start with #cloud-config or #!/.")
    return text


def _parse_labels(pairs: list[str] | None) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise PlanError("PLAN_INVALID", f"Invalid --label (want k=v): {item!r}.")
        key, value = item.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise PlanError("PLAN_INVALID", f"Invalid --label (want k=v): {item!r}.")
        labels[key] = value
    return labels


def create_plan(name: str, server_type: str, location: str, image: str,
                ssh_keys: list[str], user_data_path: str | None = None,
                labels: list[str] | None = None,
                planned_context: str | None = None) -> dict:
    keys = sorted({k.strip() for k in (ssh_keys or []) if k.strip()})
    if not keys:
        raise PlanError("PLAN_INVALID", "At least one --ssh-key is required.")
    binding = (planned_context or "").strip() or None
    payload: dict = {
        "version": PLAN_VERSION,
        "tool": TOOL,
        "name": validate_name(name),
        "server_type": (server_type or "").strip(),
        "location": (location or "").strip(),
        "image": (image or "").strip(),
        "ssh_keys": keys,
        "planned_context": binding,
        "user_data": None,
        "user_data_sha256": None,
        "labels": _parse_labels(labels),
        "created_at": utcnow_iso(),
        "tool_version": __version__,
    }
    if not payload["server_type"] or not payload["location"] or not payload["image"]:
        raise PlanError("PLAN_INVALID", "type, location, and image are required.")
    if user_data_path:
        raw = Path(user_data_path).read_bytes()
        text = validate_user_data(raw)
        payload["user_data"] = text
        payload["user_data_sha256"] = PLAN_HASH_PREFIX + _sha_hex(raw)
    return {"plan": payload, "plan_hash": plan_hash_of(payload)}


def write_plan_file(plan_obj: dict, out_path: str) -> str:
    target = Path(out_path).expanduser()
    if target.exists():
        raise PlanError("PLAN_EXISTS", f"Refusing to overwrite plan file: {target}.")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(plan_obj, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return str(target)


def load_plan(plan_path: str, expected_hash: str | None = None,
              max_age_hours: float | None = DEFAULT_MAX_AGE_HOURS) -> tuple[dict, str]:
    try:
        raw = Path(plan_path).read_text(encoding="utf-8")
        obj = json.loads(raw)
    except FileNotFoundError:
        raise PlanError("PLAN_NOT_FOUND", f"Plan file not found: {plan_path}.") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError("PLAN_INVALID", f"Plan file unreadable: {exc}.") from None
    payload = obj.get("plan") if isinstance(obj, dict) else None
    embedded = obj.get("plan_hash") if isinstance(obj, dict) else None
    if not isinstance(payload, dict) or not isinstance(embedded, str):
        raise PlanError("PLAN_INVALID", "Plan file must contain {plan, plan_hash}.")
    if payload.get("version") != PLAN_VERSION:
        raise PlanError("PLAN_VERSION", "Unsupported plan version.")
    if plan_hash_of(payload) != embedded:
        raise PlanError("PLAN_TAMPERED", "Plan file was modified after review (hash mismatch).")
    # None skips approval comparison (preflight only). Create must pass a
    # nonempty formatted sha256; empty string never bypasses.
    if expected_hash is not None:
        want = expected_hash.strip() if isinstance(expected_hash, str) else ""
        if not _HASH_RE.match(want):
            raise PlanError("PLAN_HASH_MISMATCH",
                            "Given --plan-hash must be nonempty sha256:<64 hex>.")
        if want != embedded:
            raise PlanError("PLAN_HASH_MISMATCH",
                            "Given --plan-hash does not match the reviewed plan.")
    user_data = payload.get("user_data")
    digest = payload.get("user_data_sha256")
    if user_data is not None:
        if not isinstance(user_data, str) or not isinstance(digest, str):
            raise PlanError("PLAN_TAMPERED", "user-data digest block is malformed.")
        actual = PLAN_HASH_PREFIX + _sha_hex(user_data.encode("utf-8"))
        if actual != digest:
            raise PlanError("PLAN_TAMPERED", "user-data digest mismatch (tampered plan).")
    if not payload.get("ssh_keys"):
        raise PlanError("PLAN_INVALID", "Plan has no SSH keys.")
    try:
        created = datetime.fromisoformat(str(payload.get("created_at", "")).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise PlanError("PLAN_INVALID", "Plan created_at is invalid.") from None
    if created.tzinfo is None:
        raise PlanError("PLAN_INVALID", "Plan created_at must be timezone-aware.")
    try:
        limit = DEFAULT_MAX_AGE_HOURS if max_age_hours is None else float(max_age_hours)
    except (ValueError, TypeError):
        raise PlanError("PLAN_INVALID", "max-plan-age must be a number.") from None
    if not math.isfinite(limit) or limit <= 0:
        raise PlanError("PLAN_INVALID", "max-plan-age must be finite and positive.")
    try:
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600.0
    except TypeError:
        raise PlanError("PLAN_INVALID", "Plan created_at is invalid.") from None
    if age_hours > limit:
        raise PlanError("PLAN_STALE", f"Plan is {age_hours:.1f}h old (limit {limit}h); re-plan and re-review.")
    if age_hours < -1:
        raise PlanError("PLAN_INVALID", "Plan created_at is in the future.")
    return payload, embedded


def enforce_planned_context(payload: dict, auth: Auth) -> None:
    """Fail if the active project selection differs from the reviewed plan."""
    binding = (payload.get("planned_context") or "").strip() or None
    active = (auth.context or "").strip() or None
    if binding:
        if active != binding:
            raise PlanError(
                "PLAN_CONTEXT_MISMATCH",
                f"Plan was reviewed for context {binding!r}; active is {active!r}.",
            )
    elif active:
        raise PlanError(
            "PLAN_CONTEXT_MISMATCH",
            "Plan was reviewed without a named context (token mode); "
            f"active context is {active!r}. Re-plan with --context to bind it.",
        )


def validate_receipt_path(receipt_path: str | None) -> None:
    """Prove the receipt is writable before any cloud write."""
    if not receipt_path:
        return
    target = Path(receipt_path).expanduser()
    if target.exists():
        raise CreateError("RECEIPT_EXISTS", f"Refusing to overwrite receipt: {target}.")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CreateError("RECEIPT_PATH_INVALID", f"Receipt dir not writable: {exc}.") from None
    probe = target.parent / f".lh-receipt-probe-{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
    except OSError as exc:
        raise CreateError("RECEIPT_PATH_INVALID", f"Receipt path not writable: {exc}.") from None
    finally:
        try:
            probe.unlink()
        except OSError:
            pass


def _names(items: list, *fields: str) -> set[str]:
    out: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        for field in fields:
            value = item.get(field)
            if isinstance(value, str) and value:
                out.add(value)
            elif isinstance(value, int) and field == "id":
                out.add(str(value))
    return out


def _find(items: list, value: str) -> dict | None:
    want = (value or "").strip()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("name") == want or str(item.get("id", "")) == want:
            return item
    return None


def _find_image(images: list, value: str, type_arch: str | None) -> dict | None:
    """Select image by name/id; on duplicate names prefer type arch.

    Observed: ubuntu-24.04 ships as two same-name records (x86, arm).
    First-match yields false arch mismatch for cax (arm) types. An exact
    numeric ID pins that record and may fail incompatible, as it should.
    """
    want = (value or "").strip()
    candidates = [i for i in images
                  if isinstance(i, dict)
                  and (i.get("name") == want or str(i.get("id", "")) == want)]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    exact = [i for i in candidates if str(i.get("id", "")) == want]
    if exact:
        return exact[0]
    if type_arch:
        for item in candidates:
            if str(item.get("architecture", "") or "").strip().lower() == type_arch:
                return item
    return candidates[0]


def _location_entry_matches(entry: dict, want: str) -> bool:
    """Match hcloud 1.61 ({id,name}) and newer ({location,...}) shapes."""
    if not isinstance(entry, dict):
        return False
    if entry.get("location") == want or entry.get("name") == want:
        return True
    return str(entry.get("id", "")) == want


def _is_deprecated(obj: dict) -> bool:
    # Current schema: deprecation object (image.deprecation,
    # server_type.locations[].deprecation). Legacy boolean tolerated.
    dep = obj.get("deprecation")
    if isinstance(dep, dict):
        return bool(dep)
    if dep is not None:
        return True
    return bool(obj.get("deprecated", False))


def preflight(payload: dict, auth: Auth, hcloud_bin: str = "hcloud",
              timeout: int | float | None = None, runner_json=run_json) -> dict:
    """Live read-only checks; no writes."""
    require_live_auth(auth)
    enforce_planned_context(payload, auth)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": redact_text(detail)})

    def probe(argv: list[str], what: str) -> list:
        raw = runner_json(argv, auth, timeout=timeout, hcloud_bin=hcloud_bin)
        if not isinstance(raw, list):
            raise HCloudError("HCLOUD_BAD_JSON",
                              f"Unexpected {what} JSON shape: {type(raw).__name__}; "
                              f"refusing false pass.")
        return raw

    server_list = probe(["server", "list", "-o", "json"], "server list")
    taken = payload["name"] in _names(server_list, "name")
    check("name_available", not taken,
          f"name {payload['name']!r} already exists." if taken else f"name {payload['name']!r} is free.")

    type_list = probe(["server-type", "list", "-o", "json"], "server-type list")
    type_obj = _find(type_list, payload["server_type"])
    check("server_type_exists", type_obj is not None,
          f"type {payload['server_type']!r} {'found' if type_obj else 'missing'}.")

    location_list = probe(["location", "list", "-o", "json"], "location list")
    ok = _find(location_list, payload["location"]) is not None
    check("location_exists", ok, f"location {payload['location']!r} {'found' if ok else 'missing'}.")

    image_list = probe(["image", "list", "-o", "json"], "image list")
    _early_type_arch = ""
    if type_obj is not None:
        _early_type_arch = str(type_obj.get("architecture", "") or "").strip().lower() or ""
    image_obj = _find_image(image_list, payload["image"], _early_type_arch or None)
    check("image_exists", image_obj is not None,
          f"image {payload['image']!r} {'found' if image_obj else 'missing'}.")

    key_list = probe(["ssh-key", "list", "-o", "json"], "ssh-key list")
    missing = [k for k in payload.get("ssh_keys", []) if _find(key_list, k) is None]
    check("ssh_keys_exist", not missing,
          f"missing ssh-keys: {', '.join(missing)}." if missing else f"{len(payload.get('ssh_keys', []))} ssh-key(s) found.")

    # Location support + availability from server_type.locations[].
    # hcloud 1.61: [{id,name,deprecation}]; newer adds available/recommended.
    loc_entry: dict | None = None
    loc_data_note: str | None = None
    if type_obj is None:
        check("location_supported", False, "type missing; cannot check location support.")
    else:
        locs = type_obj.get("locations")
        if not isinstance(locs, list):
            loc_data_note = ("support data missing (no locations[]); "
                             "cannot verify support; blocking.")
            check("location_supported", False, loc_data_note)
        else:
            for entry in locs:
                if _location_entry_matches(entry, payload["location"]):
                    loc_entry = entry
                    break
            if loc_entry is None:
                check("location_supported", False,
                      f"type {payload['server_type']!r} does not support location {payload['location']!r}.")
            else:
                check("location_supported", True,
                      f"type {payload['server_type']!r} supports {payload['location']!r}.")

    if loc_entry is not None:
        avail = loc_entry.get("available")
        if avail is False:
            check("location_available", False,
                  f"location {payload['location']!r} reports available=false for "
                  f"{payload['server_type']!r} (no capacity).")
        elif avail is True:
            check("location_available", True,
                  "available=true is capacity indication, not guarantee.")
        else:
            check("location_available", True,
                  "availability unknown (hcloud without available field); "
                  "assuming supported, capacity indication unavailable.")
        if _is_deprecated(loc_entry):
            check("location_not_deprecated", False,
                  f"type {payload['server_type']!r} is deprecated in {payload['location']!r}.")
        else:
            check("location_not_deprecated", True, "type/location not deprecated.")
    elif loc_data_note is not None:
        check("location_available", False, loc_data_note)
        check("location_not_deprecated", False, loc_data_note)

    if image_obj is not None:
        if _is_deprecated(image_obj):
            check("image_not_deprecated", False, f"image {payload['image']!r} is deprecated.")
        else:
            check("image_not_deprecated", True, "image not deprecated.")
    else:
        check("image_not_deprecated", False, "image missing; cannot check deprecation.")

    if type_obj is not None and image_obj is not None:
        type_arch = str(type_obj.get("architecture", "") or "").strip().lower()
        image_arch = str(image_obj.get("architecture", "") or "").strip().lower()
        if not type_arch or not image_arch:
            check("arch_compatible", False,
                  "architecture unknown (missing type/image architecture); blocking.")
        elif type_arch == image_arch:
            check("arch_compatible", True, f"architecture {type_arch} matches.")
        else:
            check("arch_compatible", False,
                  f"architecture mismatch: type {type_arch} vs image {image_arch}.")
    else:
        check("arch_compatible", False, "type or image missing; cannot check architecture.")

    failures = [c for c in checks if not c["ok"]]
    return {"passed": not failures, "checks": checks, "failures": failures}


def _field_matches(obj_val, want: str) -> bool | None:
    """True if matches, False if present-but-different, None if absent."""
    if obj_val is None or obj_val == "":
        return None
    if isinstance(obj_val, dict):
        names = {str(v) for v in (obj_val.get("name"), obj_val.get("id")) if v not in (None, "")}
        if not names:
            return None
        return str(want) in names
    if isinstance(obj_val, str):
        return obj_val == str(want)
    return str(obj_val) == str(want)


def _readback(selector: str, auth: Auth, hcloud_bin: str,
              timeout: int | float | None, runner_json,
              expected_id=None, expected_name: str | None = None,
              payload: dict | None = None) -> dict:
    """Confirm a server via describe; validate id/name and plan fields.

    Direct shape {id,name,...} and nested {server:{...}} both checked;
    nested alone never counts without id/name match. Invalid shapes stay
    unknown (found None), never false missing.
    """
    try:
        data = runner_json(["server", "describe", selector, "-o", "json"], auth,
                           timeout=timeout, hcloud_bin=hcloud_bin)
    except HCloudError as exc:
        return {"ok": False, "found": None, "detail": redact_text(str(exc))}
    obj = None
    if isinstance(data, dict):
        nested = data.get("server")
        obj = nested if isinstance(nested, dict) else data
    if not isinstance(obj, dict) or not obj:
        return {"ok": False, "found": None,
                "detail": f"describe {selector!r} returned unexpected shape."}
    if expected_id is not None and str(obj.get("id", "")) != str(expected_id):
        return {"ok": True, "found": False,
                "detail": f"describe id {obj.get('id')!r} != expected {expected_id!r}."}
    if expected_name is not None and obj.get("name") != expected_name:
        return {"ok": True, "found": False,
                "detail": f"describe name {obj.get('name')!r} != expected {expected_name!r}."}
    if payload is not None:
        mismatches: list[str] = []
        for plan_key, obj_keys in (("server_type", ("server_type", "type")),
                                   ("location", ("location",)),
                                   ("image", ("image",))):
            want = payload.get(plan_key)
            if not want:
                continue
            result: bool | None = None
            for key in obj_keys:
                if key in obj:
                    result = _field_matches(obj.get(key), str(want))
                    break
            if result is False:
                mismatches.append(f"{plan_key} {obj.get(obj_keys[0])!r} != {want!r}")
        if mismatches:
            return {"ok": True, "found": False,
                    "detail": "plan mismatch: " + "; ".join(mismatches) + "."}
    label = expected_name or (str(expected_id) if expected_id is not None else selector)
    return {"ok": True, "found": True, "detail": f"server {label!r} confirmed."}


def _receipt(payload: dict, plan_hash: str, status: str, dry_run: bool,
             preflight_result: dict | None, server: dict | None,
             error: str | None, readback: dict | None, auth: Auth) -> dict:
    return redact_obj({
        "tool": TOOL,
        "version": __version__,
        "created_at": utcnow_iso(),
        "plan_hash": plan_hash,
        "plan_name": payload.get("name"),
        "user_data_sha256": payload.get("user_data_sha256"),
        "status": status,
        "dry_run": dry_run,
        "preflight": preflight_result,
        "server": server,
        "error": error,
        "readback": readback,
        "auth_source": auth.source if not auth.context else f"context:{auth.context}",
        "provision_support": PROVISION_SUPPORT,
    })


def _write_receipt_file(receipt: dict, receipt_path: str | None) -> str | None:
    if not receipt_path:
        return None
    target = Path(receipt_path).expanduser()
    if target.exists():
        raise CreateError("RECEIPT_EXISTS", f"Refusing to overwrite receipt: {target}.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return str(target)


def _uncertain_status(readback: dict) -> str:
    if readback.get("found") is True:
        return "uncertain_exists"
    if readback.get("found") is None:
        return "uncertain_unknown"
    return "uncertain_missing"


def create_from_plan(plan_path: str, expected_hash: str, approve: bool, dry_run: bool,
                     receipt_path: str | None, max_age_hours: float | None,
                     auth: Auth, hcloud_bin: str = "hcloud",
                     timeout: int | float | None = None,
                     runner_json=run_json, runner=run) -> dict:
    """One CLI invocation; no client-side retry; honest uncertain handling."""
    if expected_hash is None or not str(expected_hash).strip():
        raise PlanError("PLAN_HASH_MISMATCH",
                        "Create requires nonempty --plan-hash matching the reviewed plan.")
    payload, plan_hash = load_plan(plan_path, expected_hash, max_age_hours)
    if not approve:
        raise PlanError("NEED_APPROVAL", "Refusing without explicit --approve.")
    require_live_auth(auth)
    enforce_planned_context(payload, auth)
    validate_receipt_path(receipt_path)
    try:
        flight = preflight(payload, auth, hcloud_bin, timeout, runner_json)
    except HCloudError as exc:
        receipt = _receipt(payload, plan_hash, "blocked", dry_run, None, None,
                           redact_text(str(exc)), None, auth)
        _write_receipt_file(receipt, receipt_path)
        raise PreflightBlocked(f"Preflight probe failed: {exc}", []) from exc
    if not flight["passed"]:
        receipt = _receipt(payload, plan_hash, "blocked", dry_run, flight, None,
                           "Preflight failed; no write attempted.", None, auth)
        _write_receipt_file(receipt, receipt_path)
        raise PreflightBlocked("Preflight failed; no write attempted.", flight["checks"])
    if dry_run:
        receipt = _receipt(payload, plan_hash, "dry_run", True, flight, None, None, None, auth)
        _write_receipt_file(receipt, receipt_path)
        return receipt

    argv: list[str] = ["server", "create", "--name", payload["name"],
                      "--type", payload["server_type"], "--location", payload["location"],
                      "--image", payload["image"]]
    for key in payload.get("ssh_keys", []):
        argv += ["--ssh-key", key]
    for k, v in (payload.get("labels") or {}).items():
        argv += ["--label", f"{k}={v}"]
    tmp_userdata: str | None = None
    if payload.get("user_data"):
        # Private snapshot of the reviewed bytes; re-verify digest at send time
        # so there is no TOCTOU between plan review and CLI load.
        send_bytes = str(payload["user_data"]).encode("utf-8")
        if PLAN_HASH_PREFIX + _sha_hex(send_bytes) != payload.get("user_data_sha256"):
            raise PlanError("PLAN_TAMPERED", "user-data bytes do not match reviewed digest.")
        handle = tempfile.NamedTemporaryFile(mode="wb", prefix="lh-userdata-", delete=False)
        try:
            try:
                os.chmod(handle.name, 0o600)
            except OSError:
                pass
            handle.write(send_bytes)
        finally:
            handle.close()
        tmp_userdata = handle.name
        argv += ["--user-data-from-file", tmp_userdata]
    argv += ["-o", "json"]
    try:
        # One CLI invocation: no loop, no client-side retry.
        stdout = runner(argv, auth, timeout=timeout, hcloud_bin=hcloud_bin)
    except HCloudError as exc:
        readback = _readback(payload["name"], auth, hcloud_bin, timeout, runner_json,
                             expected_name=payload["name"])
        detail = redact_text(str(exc) + (f" | {exc.stderr}" if exc.stderr else ""))
        if exc.code == "TIMEOUT":
            status = _uncertain_status(readback)
            receipt = _receipt(payload, plan_hash, status, False, flight, None,
                               f"Create timed out; see readback (no false success): {detail}",
                               readback, auth)
            _write_receipt_file(receipt, receipt_path)
            raise UncertainError(status.upper(), receipt["error"], readback) from exc
        if readback.get("found") is True:
            receipt = _receipt(payload, plan_hash, "uncertain_exists", False, flight, None,
                               f"Create CLI failed but server exists; needs review: {detail}",
                               readback, auth)
            _write_receipt_file(receipt, receipt_path)
            raise UncertainError("UNCERTAIN_EXISTS", receipt["error"], readback) from exc
        if readback.get("found") is None:
            receipt = _receipt(payload, plan_hash, "uncertain_unknown", False, flight, None,
                               f"Create failed and readback inconclusive: {detail}",
                               readback, auth)
            _write_receipt_file(receipt, receipt_path)
            raise UncertainError("UNCERTAIN_UNKNOWN", receipt["error"], readback) from exc
        receipt = _receipt(payload, plan_hash, "failed", False, flight, None, detail, readback, auth)
        _write_receipt_file(receipt, receipt_path)
        raise CreateError(exc.code, str(exc)) from exc
    finally:
        if tmp_userdata:
            try:
                os.unlink(tmp_userdata)
            except OSError:
                pass
    try:
        created = json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        readback = _readback(payload["name"], auth, hcloud_bin, timeout, runner_json,
                             expected_name=payload["name"])
        status = _uncertain_status(readback)
        receipt = _receipt(payload, plan_hash, status, False, flight, None,
                           "Create returned invalid JSON; see readback (no false success).",
                           readback, auth)
        _write_receipt_file(receipt, receipt_path)
        raise UncertainError(status.upper(), receipt["error"], readback) from None
    server_obj = created.get("server") if isinstance(created, dict) else None
    server_id = server_obj.get("id") if isinstance(server_obj, dict) else None
    if server_id is None:
        readback = _readback(payload["name"], auth, hcloud_bin, timeout, runner_json,
                             expected_name=payload["name"])
        status = _uncertain_status(readback)
        receipt = _receipt(payload, plan_hash, status, False, flight, None,
                           "Create response lacked a server id; see readback (no false success).",
                           readback, auth)
        _write_receipt_file(receipt, receipt_path)
        raise UncertainError(status.upper(), receipt["error"], readback)
    readback = _readback(str(server_id), auth, hcloud_bin, timeout, runner_json,
                             expected_id=server_id, expected_name=payload["name"],
                             payload=payload)
    if readback.get("found") is not True:
        receipt = _receipt(payload, plan_hash, "uncertain_unknown", False, flight,
                           redact_obj(server_obj), "Readback did not confirm create (no false success).",
                           readback, auth)
        _write_receipt_file(receipt, receipt_path)
        raise UncertainError("UNCERTAIN_UNKNOWN", receipt["error"], readback)
    receipt = _receipt(payload, plan_hash, "created", False, flight,
                       redact_obj(server_obj), None, readback, auth)
    _write_receipt_file(receipt, receipt_path)
    return receipt
