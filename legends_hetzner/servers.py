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
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import PROVISION_SUPPORT, TOOL, __version__
from .hcloud import Auth, HCloudError, redact_obj, redact_text, require_live_auth, run, run_json

PLAN_VERSION = 1
PLAN_HASH_PREFIX = "sha256:"
DEFAULT_MAX_AGE_HOURS = 24
MAX_USERDATA_BYTES = 32768
MAX_PLAN_BYTES = 1_048_576  # 1 MB cap for plan JSON files

_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,61}[A-Za-z0-9])?$")
_IDENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CONTEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_DARWIN_SYSTEM_SYMLINKS = (Path("/var"), Path("/tmp"), Path("/etc"))
_CFA_PROTECTED_FOLDERS = (
    "Desktop",
    "Documents",
    "Pictures",
    "Music",
    "Videos",
    "Favorites",
    "OneDrive",
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, val in pairs:
        if key in out:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        out[key] = val
    return out


def check_no_symlink_chain(path: Path, exc_cls, code: str, message: str) -> None:
    """Reject symlink/reparse targets across the full ancestor chain.

    Exempts standard macOS system root symlinks (/var, /tmp, /etc).
    """
    current = path.expanduser()
    if not current.is_absolute():
        current = Path.cwd() / current
    for candidate in (current, *current.parents):
        if sys.platform == "darwin" and candidate in _DARWIN_SYSTEM_SYMLINKS:
            continue
        try:
            if candidate.is_symlink():
                raise exc_cls(code, message)
        except OSError:
            continue


def check_not_cfa_protected(path: Path, exc_cls, code: str) -> None:
    """Refuse writing into Windows Controlled Folder Access (CFA) directories."""
    if os.name != "nt":
        return
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser()
    roots: list[Path] = []
    for env_key in ("USERPROFILE", "OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        val = (os.environ.get(env_key) or "").strip()
        if val:
            try:
                roots.append(Path(val).resolve())
            except OSError:
                roots.append(Path(val))
    for root in roots:
        if root.name.lower() == "onedrive":
            if resolved == root or root in resolved.parents:
                raise exc_cls(
                    code,
                    f"Refusing to write inside Windows Controlled Folder Access path: {path}",
                )
        for folder in _CFA_PROTECTED_FOLDERS:
            protected = root / folder
            if resolved == protected or protected in resolved.parents:
                raise exc_cls(
                    code,
                    f"Refusing to write inside Windows Controlled Folder Access path: {path}",
                )


def _read_bounded_bytes(path: Path, max_bytes: int, exc_cls, not_found_code: str, invalid_code: str, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        raise exc_cls(not_found_code, f"{label} not found: {path}.") from None
    except OSError as exc:
        raise exc_cls(invalid_code, f"{label} unreadable: {exc}.") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise exc_cls(invalid_code, f"{label} must be a regular file: {path}.")
        if st.st_size > max_bytes:
            raise exc_cls(invalid_code, f"{label} exceeds {max_bytes} bytes.")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise exc_cls(invalid_code, f"{label} exceeds {max_bytes} bytes.")
        return b"".join(chunks)
    finally:
        os.close(fd)


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


def validate_identifier(value: str, field: str) -> str:
    cleaned = (value or "").strip() if isinstance(value, str) else ""
    if not cleaned or not _IDENT_RE.match(cleaned):
        raise PlanError("PLAN_INVALID", f"Invalid {field}: {value!r}.")
    return cleaned


def validate_context_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = (value if isinstance(value, str) else "").strip()
    if not cleaned:
        return None
    if not _CONTEXT_RE.match(cleaned):
        raise PlanError("PLAN_INVALID", f"Invalid context name: {value!r}.")
    return cleaned


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
        if not isinstance(item, str) or "=" not in item:
            raise PlanError("PLAN_INVALID", f"Invalid --label (want k=v): {item!r}.")
        key, value = item.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not value or not _IDENT_RE.match(key) or not _IDENT_RE.match(value):
            raise PlanError("PLAN_INVALID", f"Invalid --label (want k=v): {item!r}.")
        labels[key] = value
    return labels


def create_plan(name: str, server_type: str, location: str, image: str,
                ssh_keys: list[str], user_data_path: str | None = None,
                labels: list[str] | None = None,
                planned_context: str | None = None) -> dict:
    raw_keys = [k.strip() for k in (ssh_keys or []) if isinstance(k, str) and k.strip()]
    if not raw_keys:
        raise PlanError("PLAN_INVALID", "At least one --ssh-key is required.")
    keys = sorted({validate_identifier(k, "ssh_key") for k in raw_keys})
    binding = validate_context_name(planned_context)
    st_val = (server_type or "").strip()
    loc_val = (location or "").strip()
    img_val = (image or "").strip()
    if not st_val or not loc_val or not img_val:
        raise PlanError("PLAN_INVALID", "type, location, and image are required.")
    payload: dict = {
        "version": PLAN_VERSION,
        "tool": TOOL,
        "name": validate_name(name),
        "server_type": validate_identifier(st_val, "server_type"),
        "location": validate_identifier(loc_val, "location"),
        "image": validate_identifier(img_val, "image"),
        "ssh_keys": keys,
        "planned_context": binding,
        "user_data": None,
        "user_data_sha256": None,
        "labels": _parse_labels(labels),
        "created_at": utcnow_iso(),
        "tool_version": __version__,
    }
    if user_data_path:
        ud_path = Path(user_data_path)
        check_no_symlink_chain(
            ud_path, PlanError, "USERDATA_INVALID", "Refusing symlinked --user-data path."
        )
        raw = _read_bounded_bytes(
            ud_path,
            MAX_USERDATA_BYTES,
            PlanError,
            "USERDATA_INVALID",
            "USERDATA_INVALID",
            "user-data",
        )
        text = validate_user_data(raw)
        payload["user_data"] = text
        payload["user_data_sha256"] = PLAN_HASH_PREFIX + _sha_hex(raw)
    return {"plan": payload, "plan_hash": plan_hash_of(payload)}


def write_plan_file(plan_obj: dict, out_path: str, *, overwrite: bool = False) -> str:
    target = Path(out_path).expanduser()
    check_no_symlink_chain(
        target, PlanError, "PLAN_INVALID", f"Refusing symlinked plan output path: {target}."
    )
    check_not_cfa_protected(target, PlanError, "PLAN_INVALID")
    if not overwrite and target.exists():
        raise PlanError("PLAN_EXISTS", f"Refusing to overwrite plan file: {target}.")
    target.parent.mkdir(parents=True, exist_ok=True)
    check_no_symlink_chain(
        target, PlanError, "PLAN_INVALID", f"Refusing symlinked plan output path: {target}."
    )
    encoded = (json.dumps(plan_obj, indent=2) + "\n").encode("utf-8")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | (os.O_TRUNC if overwrite else os.O_EXCL)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(str(target), flags, 0o600)
    except FileExistsError:
        raise PlanError("PLAN_EXISTS", f"Refusing to overwrite plan file: {target}.") from None
    except OSError as exc:
        raise PlanError("PLAN_INVALID", f"Cannot write plan file {target}: {exc}.") from None
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
    return str(target)


def load_plan(plan_path: str, expected_hash: str | None = None,
              max_age_hours: float | None = DEFAULT_MAX_AGE_HOURS) -> tuple[dict, str]:
    source = Path(plan_path)
    check_no_symlink_chain(
        source, PlanError, "PLAN_INVALID", f"Refusing symlinked plan file: {plan_path}."
    )
    raw_bytes = _read_bounded_bytes(
        source, MAX_PLAN_BYTES, PlanError, "PLAN_NOT_FOUND", "PLAN_INVALID", "Plan file"
    )
    try:
        raw = raw_bytes.decode("utf-8")
        obj = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
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
    validate_name(str(payload.get("name") or ""))
    validate_identifier(str(payload.get("server_type") or ""), "server_type")
    validate_identifier(str(payload.get("location") or ""), "location")
    validate_identifier(str(payload.get("image") or ""), "image")
    if payload.get("planned_context") is not None:
        validate_context_name(str(payload.get("planned_context")))
    ssh_keys = payload.get("ssh_keys")
    if not isinstance(ssh_keys, list) or not ssh_keys:
        raise PlanError("PLAN_INVALID", "Plan has no SSH keys.")
    for k in ssh_keys:
        if not isinstance(k, str):
            raise PlanError("PLAN_INVALID", "Invalid SSH key entry in plan.")
        validate_identifier(k, "ssh_key")
    labels_obj = payload.get("labels")
    if labels_obj is not None:
        if not isinstance(labels_obj, dict):
            raise PlanError("PLAN_INVALID", "Plan labels must be an object.")
        for lk, lv in labels_obj.items():
            if not isinstance(lk, str) or not isinstance(lv, str):
                raise PlanError("PLAN_INVALID", "Plan labels must be string key/value pairs.")
            validate_identifier(lk, "label key")
            validate_identifier(lv, "label value")
    user_data = payload.get("user_data")
    digest = payload.get("user_data_sha256")
    if user_data is not None:
        if not isinstance(user_data, str) or not isinstance(digest, str):
            raise PlanError("PLAN_TAMPERED", "user-data digest block is malformed.")
        actual = PLAN_HASH_PREFIX + _sha_hex(user_data.encode("utf-8"))
        if actual != digest:
            raise PlanError("PLAN_TAMPERED", "user-data digest mismatch (tampered plan).")
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


def validate_receipt_path(receipt_path: str | None, *, overwrite: bool = False) -> None:
    """Prove the receipt is writable before any cloud write."""
    if not receipt_path:
        return
    target = Path(receipt_path).expanduser()
    check_no_symlink_chain(
        target, CreateError, "RECEIPT_PATH_INVALID", f"Refusing symlinked receipt path: {target}."
    )
    check_not_cfa_protected(target, CreateError, "RECEIPT_PATH_INVALID")
    if not overwrite and target.exists():
        raise CreateError("RECEIPT_EXISTS", f"Refusing to overwrite receipt: {target}.")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CreateError("RECEIPT_PATH_INVALID", f"Receipt dir not writable: {exc}.") from None
    check_no_symlink_chain(
        target, CreateError, "RECEIPT_PATH_INVALID", f"Refusing symlinked receipt path: {target}."
    )
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
              timeout: int | float | None = None, runner_json=None,
              *, require_known_availability: bool = False,
              allow_unavailable: bool = False) -> dict:
    """Live read-only checks; no writes."""
    if runner_json is None:
        runner_json = run_json
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
            if allow_unavailable:
                check("location_available", True,
                      f"location {payload['location']!r} reports catalog available=false for "
                      f"{payload['server_type']!r}, bypassed via --allow-unavailable to attempt "
                      f"direct API placement.")
            else:
                check("location_available", False,
                      f"location {payload['location']!r} reports available=false for "
                      f"{payload['server_type']!r} (no capacity; pass --allow-unavailable to "
                      f"attempt direct API placement anyway).")
        elif avail is True:
            check("location_available", True,
                  "available=true is capacity indication, not guarantee.")
        elif require_known_availability and not allow_unavailable:
            check("location_available", False,
                  "availability unknown (hcloud without available field); "
                  "snipe requires confirmed available=true capacity.")
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
    sel = (selector or "").strip() if isinstance(selector, str) else ""
    if not sel or not _IDENT_RE.match(sel):
        return {
            "ok": False,
            "found": None,
            "detail": f"Invalid selector {selector!r}; refusing describe.",
        }
    try:
        data = runner_json(["server", "describe", "-o", "json", "--", sel], auth,
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
             error: str | None, readback: dict | None, auth: Auth,
             snipe_meta: dict | None = None) -> dict:
    raw = {
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
    }
    if snipe_meta is not None:
        raw["snipe"] = snipe_meta
    return redact_obj(raw)


def _write_receipt_file(receipt: dict, receipt_path: str | None, *, overwrite: bool = False) -> str | None:
    if not receipt_path:
        return None
    target = Path(receipt_path).expanduser()
    check_no_symlink_chain(
        target, CreateError, "RECEIPT_PATH_INVALID", f"Refusing symlinked receipt path: {target}."
    )
    check_not_cfa_protected(target, CreateError, "RECEIPT_PATH_INVALID")
    if not overwrite and target.exists():
        raise CreateError("RECEIPT_EXISTS", f"Refusing to overwrite receipt: {target}.")
    target.parent.mkdir(parents=True, exist_ok=True)
    check_no_symlink_chain(
        target, CreateError, "RECEIPT_PATH_INVALID", f"Refusing symlinked receipt path: {target}."
    )
    encoded = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | (os.O_TRUNC if overwrite else os.O_EXCL)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(str(target), flags, 0o600)
    except FileExistsError:
        raise CreateError("RECEIPT_EXISTS", f"Refusing to overwrite receipt: {target}.") from None
    except OSError as exc:
        raise CreateError("RECEIPT_PATH_INVALID", f"Cannot write receipt {target}: {exc}.") from None
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
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
                     runner_json=None, runner=None,
                     *, allow_unavailable: bool = False,
                     _preverified_flight: dict | None = None,
                     _snipe_meta: dict | None = None) -> dict:
    """One CLI invocation; no client-side retry; honest uncertain handling."""
    if runner_json is None:
        runner_json = run_json
    if runner is None:
        runner = run
    if expected_hash is None or not str(expected_hash).strip():
        raise PlanError("PLAN_HASH_MISMATCH",
                        "Create requires nonempty --plan-hash matching the reviewed plan.")
    payload, plan_hash = load_plan(plan_path, expected_hash, max_age_hours)
    if not approve:
        raise PlanError("NEED_APPROVAL", "Refusing without explicit --approve.")
    require_live_auth(auth)
    enforce_planned_context(payload, auth)
    validate_receipt_path(receipt_path)
    if _preverified_flight is not None:
        flight = _preverified_flight
    else:
        try:
            flight = preflight(payload, auth, hcloud_bin, timeout, runner_json,
                               allow_unavailable=allow_unavailable)
        except HCloudError as exc:
            receipt = _receipt(payload, plan_hash, "blocked", dry_run, None, None,
                               redact_text(str(exc)), None, auth, snipe_meta=_snipe_meta)
            _write_receipt_file(receipt, receipt_path)
            raise PreflightBlocked(f"Preflight probe failed: {exc}", []) from exc
    if not flight["passed"]:
        receipt = _receipt(payload, plan_hash, "blocked", dry_run, flight, None,
                           "Preflight failed; no write attempted.", None, auth,
                           snipe_meta=_snipe_meta)
        _write_receipt_file(receipt, receipt_path)
        raise PreflightBlocked("Preflight failed; no write attempted.", flight["checks"])
    if dry_run:
        receipt = _receipt(payload, plan_hash, "dry_run", True, flight, None, None, None, auth,
                           snipe_meta=_snipe_meta)
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
                               readback, auth, snipe_meta=_snipe_meta)
            _write_receipt_file(receipt, receipt_path)
            raise UncertainError(status.upper(), receipt["error"], readback) from exc
        if readback.get("found") is True:
            receipt = _receipt(payload, plan_hash, "uncertain_exists", False, flight, None,
                               f"Create CLI failed but server exists; needs review: {detail}",
                               readback, auth, snipe_meta=_snipe_meta)
            _write_receipt_file(receipt, receipt_path)
            raise UncertainError("UNCERTAIN_EXISTS", receipt["error"], readback) from exc
        if readback.get("found") is None:
            receipt = _receipt(payload, plan_hash, "uncertain_unknown", False, flight, None,
                               f"Create failed and readback inconclusive: {detail}",
                               readback, auth, snipe_meta=_snipe_meta)
            _write_receipt_file(receipt, receipt_path)
            raise UncertainError("UNCERTAIN_UNKNOWN", receipt["error"], readback) from exc
        receipt = _receipt(payload, plan_hash, "failed", False, flight, None, detail, readback,
                           auth, snipe_meta=_snipe_meta)
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
                           readback, auth, snipe_meta=_snipe_meta)
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
                           readback, auth, snipe_meta=_snipe_meta)
        _write_receipt_file(receipt, receipt_path)
        raise UncertainError(status.upper(), receipt["error"], readback)
    readback = _readback(str(server_id), auth, hcloud_bin, timeout, runner_json,
                             expected_id=server_id, expected_name=payload["name"],
                             payload=payload)
    if readback.get("found") is not True:
        receipt = _receipt(payload, plan_hash, "uncertain_unknown", False, flight,
                           redact_obj(server_obj), "Readback did not confirm create (no false success).",
                           readback, auth, snipe_meta=_snipe_meta)
        _write_receipt_file(receipt, receipt_path)
        raise UncertainError("UNCERTAIN_UNKNOWN", receipt["error"], readback)
    receipt = _receipt(payload, plan_hash, "created", False, flight,
                       redact_obj(server_obj), None, readback, auth, snipe_meta=_snipe_meta)
    _write_receipt_file(receipt, receipt_path)
    return receipt
