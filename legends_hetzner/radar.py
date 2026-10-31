# SPDX-License-Identifier: MIT
"""Cost-Optimized stock radar, Fractional CTO sizing advisor, and rate-limit-safe sniper.

Provides read-only availability sweeps across Hetzner Cloud locations (with
first-class focus on the European Cost-Optimized CX/CAX line in fsn1, nbg1,
and hel1) plus a guarded, rate-limit-safe `server snipe` workflow that polls
read-only preflight at bounded, jittered intervals (>= 30s) and executes at
most one `hcloud server create` invocation the moment capacity opens.
"""

from __future__ import annotations

import random
import time
from typing import Any, Callable

from . import TOOL, __version__
from .hcloud import Auth, HCloudError, redact_text, require_live_auth, run, run_json
from .servers import (
    DEFAULT_MAX_AGE_HOURS,
    PlanError,
    PreflightBlocked,
    _is_deprecated,
    _location_entry_matches,
    _receipt,
    _write_receipt_file,
    create_from_plan,
    enforce_planned_context,
    load_plan,
    preflight,
    utcnow_iso,
    validate_receipt_path,
)

MIN_POLL_INTERVAL_SECONDS = 30
MAX_POLL_INTERVAL_SECONDS = 3600
DEFAULT_POLL_INTERVAL_SECONDS = 60
MIN_JITTER_SECONDS = 0
MAX_JITTER_SECONDS = 60
DEFAULT_JITTER_SECONDS = 10
MIN_POLLS = 1
MAX_POLLS = 120
DEFAULT_WATCH_POLLS = 30

COST_OPTIMIZED_LOCATIONS: tuple[str, ...] = ("fsn1", "nbg1", "hel1")
GERMANY_LOCATIONS: tuple[str, ...] = ("fsn1", "nbg1")
VALID_CATEGORIES: tuple[str, ...] = (
    "cost_optimized",
    "regular_purpose",
    "general_purpose",
    "all",
)
VALID_ARCHS: tuple[str, ...] = ("any", "x86", "arm")

# Fractional CTO priority ranking for Cost-Optimized tiers:
# 1. cx43 (8 vCPU / 16 GB RAM x86): ideal default for full stack + automations
# 2. cx33 (4 vCPU / 8 GB RAM x86): high-value budget sweet spot
# 3. cx23 (2 vCPU / 4 GB RAM x86): starter seat with in-place rescale path up CX ladder
# 4. cx53 (16 vCPU / 32 GB RAM x86): heavy single-box consolidation ceiling
# 5-8. cax31, cax21, cax11, cax41 (ARM64 Ampere alternatives when x86 is sold out)
CTO_PRIORITY_ORDER: tuple[str, ...] = (
    "cx43",
    "cx33",
    "cx23",
    "cx53",
    "cax31",
    "cax21",
    "cax11",
    "cax41",
)

CTO_TIER_METADATA: dict[str, dict[str, Any]] = {
    "cx43": {
        "cto_rank": 1,
        "tier_class": "ideal_default",
        "cto_tier_role": (
            "Ideal Fractional CTO default (8 vCPU / 16 GB RAM / 160 GB NVMe x86). "
            "Best balance of cost and 16 GB RAM headroom for a consolidated single-server "
            "stack (Coolify, reverse proxy, websites, databases, and automation workers) "
            "with universal x86_64 container and binary compatibility."
        ),
    },
    "cx33": {
        "cto_rank": 2,
        "tier_class": "budget_sweet_spot",
        "cto_tier_role": (
            "High-value budget sweet spot (4 vCPU / 8 GB RAM / 80 GB NVMe x86). "
            "Delivers 2x the CPU and RAM of a CPX22 fallback at less than half the cost; "
            "ideal upgrade target from CX23 or in-place rescale target from an 80 GB CPX22."
        ),
    },
    "cx23": {
        "cto_rank": 3,
        "tier_class": "starter_seat",
        "cto_tier_role": (
            "Entry x86 starter seat (2 vCPU / 4 GB RAM / 40 GB NVMe x86). "
            "Sufficient to stand up Coolify and a lightweight or static/Astro staging site "
            "(configure a 4 GB swapfile to absorb Node/Astro build spikes) while waiting "
            "to rescale in-place up to CX33, CX43, or CX53 in the same location."
        ),
    },
    "cx53": {
        "cto_rank": 4,
        "tier_class": "scale_up_ceiling",
        "cto_tier_role": (
            "Heavy single-box consolidation ceiling (16 vCPU / 32 GB RAM / 320 GB NVMe x86). "
            "Top of the Cost-Optimized x86 ladder; consolidating workloads onto one CX43 "
            "or CX53 is preferred over running multiple small Hetzner servers."
        ),
    },
    "cax31": {
        "cto_rank": 5,
        "tier_class": "arm_workhorse",
        "cto_tier_role": (
            "ARM64 16 GB tier (8 Ampere cores / 16 GB RAM / 160 GB NVMe). "
            "Strong non-hyperthreaded ARM throughput for native linux/arm64 stacks, "
            "but higher monthly cost than CX43 and cannot rescale in-place to x86 CX tiers."
        ),
    },
    "cax21": {
        "cto_rank": 6,
        "tier_class": "arm_mid_tier",
        "cto_tier_role": (
            "ARM64 8 GB tier (4 Ampere cores / 8 GB RAM / 80 GB NVMe). "
            "Viable when x86 CX33 is unavailable and every container supports linux/arm64, "
            "though priced higher than CX33 and locked to the ARM rescale ladder."
        ),
    },
    "cax11": {
        "cto_rank": 7,
        "tier_class": "arm_starter",
        "cto_tier_role": (
            "ARM64 starter seat (2 Ampere cores / 4 GB RAM / 40 GB NVMe). "
            "Low-cost foothold when CX23 is sold out and no x86-only binaries are needed; "
            "cannot rescale in-place to x86 CX tiers."
        ),
    },
    "cax41": {
        "cto_rank": 8,
        "tier_class": "arm_ceiling",
        "cto_tier_role": (
            "ARM64 ceiling tier (16 Ampere cores / 32 GB RAM / 320 GB NVMe). "
            "High steady-state ARM compute, though pricier than x86 CX53."
        ),
    },
}

CTO_DOCTRINE: dict[str, Any] = {
    "preferred_line": "cost_optimized",
    "cost_optimized_locations": list(COST_OPTIMIZED_LOCATIONS),
    "germany_locations": list(GERMANY_LOCATIONS),
    "x86_ladder": ["cx23", "cx33", "cx43", "cx53"],
    "arm_ladder": ["cax11", "cax21", "cax31", "cax41"],
    "ideal_default": "cx43",
    "budget_sweet_spot": "cx33",
    "starter_seat": "cx23",
    "scale_up_ceiling": "cx53",
    "single_box_consolidation": (
        "Prefer consolidating workloads onto a single well-sized CX43 (16 GB) or CX53 "
        "(32 GB) rather than splitting across multiple small servers."
    ),
    "rescale_rules": [
        "In-place rescale requires the exact same location (for example fsn1 -> fsn1 or hel1 -> hel1).",
        "In-place rescale requires the exact same CPU architecture (x86 <-> x86 or arm <-> arm; CAX cannot rescale into CX).",
        "Full disk+CPU/RAM rescale requires target disk >= current disk (for example an 80 GB CPX22 can rescale in-place to an 80 GB CX33 or 160 GB CX43 in the same location, but not down to a 40 GB CX23 unless disk upgrade was omitted).",
    ],
    "api_vs_catalog_note": (
        "Catalog available=false (which grays out the Web Console UI as 'Sold out') "
        "is a cached/conservative indicator. The live placement engine behind POST /v1/servers "
        "(hcloud server create) and change_type can sometimes fulfill a CX43/CX33 request "
        "via the API even while the catalog reports available=false. Pass --allow-unavailable "
        "to server preflight, server create, or server snipe to test direct API placement "
        "after verifying all 9 non-capacity safety checks."
    ),
}


def _infer_category(server_type_obj: dict[str, Any]) -> str:
    raw = str(server_type_obj.get("category") or "").strip().lower()
    if raw:
        return raw
    name = str(server_type_obj.get("name") or "").strip().lower()
    if name.startswith(("cx", "cax")):
        return "cost_optimized"
    if name.startswith("cpx"):
        return "regular_purpose"
    if name.startswith("ccx"):
        return "general_purpose"
    return "unknown"


def _extract_location_price(
    server_type_obj: dict[str, Any], location_name: str
) -> tuple[str | None, str | None]:
    prices = server_type_obj.get("prices")
    if not isinstance(prices, list):
        return None, None
    want = location_name.strip().lower()
    for entry in prices:
        if not isinstance(entry, dict):
            continue
        loc = str(entry.get("location") or "").strip().lower()
        if loc != want:
            continue
        monthly = entry.get("price_monthly")
        hourly = entry.get("price_hourly")
        monthly_net = (
            str(monthly.get("net"))
            if isinstance(monthly, dict) and monthly.get("net") is not None
            else None
        )
        hourly_net = (
            str(hourly.get("net"))
            if isinstance(hourly, dict) and hourly.get("net") is not None
            else None
        )
        return monthly_net, hourly_net
    return None, None


def _strict_int(value: Any, default: int, error_code: str, label: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise PlanError(error_code, f"{label} must be an integer, not boolean.")
    if isinstance(value, float) and not value.is_integer():
        raise PlanError(error_code, f"{label} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        raise PlanError(error_code, f"{label} must be an integer.") from None


def validate_watch_params(
    *,
    watch: bool,
    interval: int | float | None,
    jitter: int | float | None,
    max_polls: int | None,
) -> tuple[int, int, int]:
    """Validate rate-limit-safe polling bounds (never hammer the provider API)."""
    interval_i = _strict_int(
        interval,
        DEFAULT_POLL_INTERVAL_SECONDS,
        "RADAR_INVALID_INTERVAL",
        "Poll --interval",
    )
    if (
        interval_i < MIN_POLL_INTERVAL_SECONDS
        or interval_i > MAX_POLL_INTERVAL_SECONDS
    ):
        raise PlanError(
            "RADAR_INTERVAL_TOO_LOW",
            f"Refusing poll --interval {interval_i}s: must be between "
            f"{MIN_POLL_INTERVAL_SECONDS}s and {MAX_POLL_INTERVAL_SECONDS}s "
            "to respect provider rate limits.",
        )

    jitter_i = _strict_int(
        jitter,
        DEFAULT_JITTER_SECONDS,
        "RADAR_INVALID_JITTER",
        "Poll --jitter",
    )
    if jitter_i < MIN_JITTER_SECONDS or jitter_i > MAX_JITTER_SECONDS:
        raise PlanError(
            "RADAR_JITTER_OUT_OF_RANGE",
            f"Poll --jitter must be between {MIN_JITTER_SECONDS}s and {MAX_JITTER_SECONDS}s.",
        )

    if not watch:
        if max_polls is not None:
            polls_single = _strict_int(
                max_polls, 1, "RADAR_POLLS_OUT_OF_RANGE", "--max-polls"
            )
            if polls_single != 1:
                raise PlanError(
                    "RADAR_WATCH_REQUIRED",
                    "Pass --watch when requesting --max-polls greater than 1.",
                )
        return interval_i, jitter_i, 1

    polls_i = _strict_int(
        max_polls,
        DEFAULT_WATCH_POLLS,
        "RADAR_POLLS_OUT_OF_RANGE",
        "--max-polls",
    )
    if polls_i < MIN_POLLS or polls_i > MAX_POLLS:
        raise PlanError(
            "RADAR_POLLS_OUT_OF_RANGE",
            f"--max-polls must be between {MIN_POLLS} and {MAX_POLLS}.",
        )
    return interval_i, jitter_i, polls_i


def _parse_csv_list(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = str(raw).split(",")
    out: list[str] = []
    seen: set[str] = set()
    for part in items:
        cleaned = str(part or "").strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def run_radar(
    auth: Auth,
    *,
    category: str = "cost_optimized",
    locations: str | list[str] | None = None,
    germany_only: bool = False,
    arch: str = "any",
    types: str | list[str] | None = None,
    watch: bool = False,
    interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
    jitter: int = DEFAULT_JITTER_SECONDS,
    max_polls: int | None = None,
    hcloud_bin: str = "hcloud",
    timeout: int | float | None = None,
    runner_json: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    rand_fn: Callable[[float, float], float] | None = None,
) -> dict[str, Any]:
    """Sweep live server-type stock and return CTO tier recommendations."""
    fn_json = runner_json if runner_json is not None else run_json
    fn_sleep = sleep_fn if sleep_fn is not None else time.sleep
    fn_rand = rand_fn if rand_fn is not None else random.uniform
    cat = (category or "cost_optimized").strip().lower()
    if cat not in VALID_CATEGORIES:
        raise PlanError(
            "RADAR_INVALID_FILTER",
            f"Unsupported --category {category!r}; choose from {', '.join(VALID_CATEGORIES)}.",
        )
    arch_norm = (arch or "any").strip().lower()
    if arch_norm not in VALID_ARCHS:
        raise PlanError(
            "RADAR_INVALID_FILTER",
            f"Unsupported --arch {arch!r}; choose from {', '.join(VALID_ARCHS)}.",
        )
    explicit_locs = _parse_csv_list(locations)
    if germany_only and explicit_locs:
        raise PlanError(
            "RADAR_INVALID_FILTER",
            "Do not combine --germany-only with --locations.",
        )
    if germany_only:
        target_locs = list(GERMANY_LOCATIONS)
    elif explicit_locs:
        target_locs = explicit_locs
    else:
        target_locs = list(COST_OPTIMIZED_LOCATIONS)

    requested_types = _parse_csv_list(types)
    interval_i, jitter_i, polls_limit = validate_watch_params(
        watch=watch, interval=interval, jitter=jitter, max_polls=max_polls
    )
    require_live_auth(auth)

    last_report: dict[str, Any] = {}
    for poll_idx in range(1, polls_limit + 1):
        raw_types = fn_json(
            ["server-type", "list", "-o", "json"],
            auth,
            timeout=timeout,
            hcloud_bin=hcloud_bin,
        )
        if not isinstance(raw_types, list):
            raise HCloudError(
                "HCLOUD_BAD_JSON",
                f"Unexpected server-type list JSON shape: {type(raw_types).__name__}.",
            )

        filtered: list[dict[str, Any]] = []
        for item in raw_types:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip().lower()
            if not name:
                continue
            item_cat = _infer_category(item)
            if cat != "all" and item_cat != cat:
                continue
            item_arch = str(item.get("architecture") or "").strip().lower()
            if arch_norm != "any" and item_arch != arch_norm:
                continue
            if requested_types and name not in requested_types:
                continue
            filtered.append(item)

        def _sort_key(st_obj: dict[str, Any]) -> tuple[int, int, str]:
            st_name = str(st_obj.get("name") or "").strip().lower()
            if st_name in CTO_PRIORITY_ORDER:
                return (0, CTO_PRIORITY_ORDER.index(st_name), st_name)
            if requested_types and st_name in requested_types:
                return (1, requested_types.index(st_name), st_name)
            cores = st_obj.get("cores")
            cores_i = int(cores) if isinstance(cores, (int, float)) else 999
            return (2, cores_i, st_name)

        filtered.sort(key=_sort_key)
        matched_type_names = {
            str(st_obj.get("name") or "").strip().lower() for st_obj in filtered
        }
        unmatched_types = [
            t for t in requested_types if t not in matched_type_names
        ]

        matrix: list[dict[str, Any]] = []
        available_matches: list[dict[str, Any]] = []
        direct_api_candidates: list[dict[str, Any]] = []
        for st_obj in filtered:
            st_name = str(st_obj.get("name") or "").strip().lower()
            st_arch = str(st_obj.get("architecture") or "").strip().lower()
            st_cat = _infer_category(st_obj)
            cores = st_obj.get("cores")
            memory_gb = st_obj.get("memory")
            disk_gb = st_obj.get("disk")
            meta = CTO_TIER_METADATA.get(st_name, {})
            cto_rank = meta.get("cto_rank")
            tier_class = meta.get("tier_class", "standard")
            cto_role = meta.get(
                "cto_tier_role",
                f"{st_cat} tier ({cores} vCPU / {memory_gb} GB RAM / {disk_gb} GB disk, {st_arch}).",
            )

            locs_raw = st_obj.get("locations")
            loc_list = locs_raw if isinstance(locs_raw, list) else []
            loc_map: dict[str, dict[str, Any]] = {}
            tier_direct_candidates: list[tuple[int, int, dict[str, Any]]] = []
            for loc_idx, loc_name in enumerate(target_locs):
                matched_entry: dict[str, Any] | None = None
                for entry in loc_list:
                    if _location_entry_matches(entry, loc_name):
                        matched_entry = entry
                        break
                monthly_net, hourly_net = _extract_location_price(st_obj, loc_name)
                if matched_entry is None:
                    loc_map[loc_name] = {
                        "supported": False,
                        "available": False,
                        "deprecated": False,
                        "price_monthly_net": monthly_net,
                        "price_hourly_net": hourly_net,
                    }
                else:
                    raw_avail = matched_entry.get("available")
                    avail_val: bool | str = (
                        raw_avail if isinstance(raw_avail, bool) else "unknown"
                    )
                    dep_val = _is_deprecated(matched_entry)
                    loc_map[loc_name] = {
                        "supported": True,
                        "available": avail_val,
                        "deprecated": dep_val,
                        "price_monthly_net": monthly_net,
                        "price_hourly_net": hourly_net,
                    }
                    candidate_entry = {
                        "server_type": st_name,
                        "location": loc_name,
                        "architecture": st_arch,
                        "category": st_cat,
                        "cores": cores,
                        "memory_gb": memory_gb,
                        "disk_gb": disk_gb,
                        "price_monthly_net": monthly_net,
                        "price_hourly_net": hourly_net,
                        "catalog_available": avail_val,
                        "cto_rank": cto_rank,
                        "tier_class": tier_class,
                        "cto_tier_role": cto_role,
                    }
                    if not dep_val:
                        avail_rank = 0 if avail_val is True else 1
                        tier_direct_candidates.append((avail_rank, loc_idx, candidate_entry))
                    if avail_val is True and not dep_val:
                        available_matches.append(
                            {
                                "server_type": st_name,
                                "location": loc_name,
                                "architecture": st_arch,
                                "category": st_cat,
                                "cores": cores,
                                "memory_gb": memory_gb,
                                "disk_gb": disk_gb,
                                "price_monthly_net": monthly_net,
                                "price_hourly_net": hourly_net,
                                "cto_rank": cto_rank,
                                "tier_class": tier_class,
                                "cto_tier_role": cto_role,
                            }
                        )

            tier_direct_candidates.sort(key=lambda item: (item[0], item[1]))
            direct_api_candidates.extend(item[2] for item in tier_direct_candidates)

            matrix.append(
                {
                    "name": st_name,
                    "architecture": st_arch,
                    "category": st_cat,
                    "cores": cores,
                    "memory_gb": memory_gb,
                    "disk_gb": disk_gb,
                    "cto_rank": cto_rank,
                    "tier_class": tier_class,
                    "cto_tier_role": cto_role,
                    "locations": loc_map,
                }
            )

        top_direct = direct_api_candidates[0] if direct_api_candidates else None
        if available_matches:
            workflow_note = (
                "Catalog shows open capacity in available_matches. If targeting a higher-priority "
                "tier currently marked available=false in catalog (see top_direct_api_target), "
                "you can still attempt one guarded direct API placement first using "
                "'server create --allow-unavailable' (or 'server snipe --allow-unavailable') "
                "before falling back to recommended_match."
            )
        else:
            workflow_note = (
                "Catalog reports available=false across all filtered tiers, but the live "
                "placement engine behind POST /v1/servers (hcloud server create) can still "
                "allocate capacity when catalog flags lag. Recommended workflow: "
                "(1) Plan for top_direct_api_target and attempt one guarded direct API create "
                "with 'legends-hetzner server create --plan FILE --plan-hash HASH --approve "
                "--allow-unavailable'; (2) If the placement engine returns resource_unavailable, "
                "run 'legends-hetzner server snipe' or 'radar --watch' at >=60s jittered intervals."
            )

        last_report = {
            "tool": TOOL,
            "version": __version__,
            "checked_at": utcnow_iso(),
            "watch": {
                "enabled": bool(watch),
                "polls_completed": poll_idx,
                "max_polls": polls_limit,
                "interval_seconds": interval_i,
                "jitter_seconds": jitter_i,
            },
            "filters": {
                "category": cat,
                "locations": target_locs,
                "germany_only": bool(germany_only),
                "architecture": arch_norm,
                "types": requested_types,
                "unmatched_types": unmatched_types,
            },
            "any_available": bool(available_matches),
            "available_count": len(available_matches),
            "available_matches": available_matches,
            "recommended_match": available_matches[0] if available_matches else None,
            "cto_strategy": {
                "top_direct_api_target": top_direct,
                "direct_api_candidates": direct_api_candidates,
                "recommended_workflow": workflow_note,
            },
            "matrix": matrix,
            "cto_doctrine": CTO_DOCTRINE,
        }
        if available_matches or poll_idx >= polls_limit:
            break
        delay = float(interval_i) + (
            float(fn_rand(0.0, float(jitter_i))) if jitter_i > 0 else 0.0
        )
        fn_sleep(delay)

    return last_report


def snipe_from_plan(
    plan_path: str,
    expected_hash: str,
    approve: bool,
    dry_run: bool,
    receipt_path: str | None,
    max_age_hours: float | None,
    auth: Auth,
    *,
    allow_unavailable: bool = False,
    interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
    jitter: int = DEFAULT_JITTER_SECONDS,
    max_polls: int = DEFAULT_WATCH_POLLS,
    hcloud_bin: str = "hcloud",
    timeout: int | float | None = None,
    runner_json: Callable[..., Any] | None = None,
    runner: Callable[..., str] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    rand_fn: Callable[[float, float], float] | None = None,
) -> dict[str, Any]:
    """Poll read-only preflight at safe jittered intervals and create once when capacity opens.

    Safety invariants:
    - Requires --approve and matching --plan-hash before any poll.
    - Enforces poll interval >= 30s with bounded max_polls (1..120).
    - Aborts immediately on poll 1 if any non-capacity preflight check fails
      (such as duplicate server name, missing SSH key, or wrong image arch).
    - Requires confirmed location_available=True (unknown availability blocks).
    - Performs at most ONE `hcloud server create` call when capacity opens;
      never retries a failed or uncertain write.
    """
    fn_json = runner_json if runner_json is not None else run_json
    fn_run = runner if runner is not None else run
    fn_sleep = sleep_fn if sleep_fn is not None else time.sleep
    fn_rand = rand_fn if rand_fn is not None else random.uniform
    if expected_hash is None or not str(expected_hash).strip():
        raise PlanError(
            "PLAN_HASH_MISMATCH",
            "Snipe requires nonempty --plan-hash matching the reviewed plan.",
        )
    interval_i, jitter_i, polls_limit = validate_watch_params(
        watch=True, interval=interval, jitter=jitter, max_polls=max_polls
    )
    payload, plan_hash = load_plan(plan_path, expected_hash, max_age_hours)
    if not approve:
        raise PlanError("NEED_APPROVAL", "Refusing without explicit --approve.")
    require_live_auth(auth)
    enforce_planned_context(payload, auth)
    validate_receipt_path(receipt_path)

    last_flight: dict[str, Any] | None = None
    for poll_idx in range(1, polls_limit + 1):
        # Re-verify plan freshness on each poll so a plan that expires mid-watch aborts cleanly.
        payload, plan_hash = load_plan(plan_path, expected_hash, max_age_hours)
        try:
            flight = preflight(
                payload,
                auth,
                hcloud_bin,
                timeout,
                fn_json,
                require_known_availability=not allow_unavailable,
                allow_unavailable=allow_unavailable,
            )
        except HCloudError as exc:
            snipe_meta = {
                "polls_completed": poll_idx,
                "max_polls": polls_limit,
                "interval_seconds": interval_i,
                "jitter_seconds": jitter_i,
                "reason": "preflight_probe_error",
            }
            receipt = _receipt(
                payload,
                plan_hash,
                "blocked",
                dry_run,
                None,
                None,
                redact_text(str(exc)),
                None,
                auth,
                snipe_meta=snipe_meta,
            )
            _write_receipt_file(receipt, receipt_path)
            raise PreflightBlocked(f"Preflight probe failed: {exc}", []) from exc

        last_flight = flight
        if flight["passed"]:
            snipe_meta = {
                "polls_completed": poll_idx,
                "max_polls": polls_limit,
                "interval_seconds": interval_i,
                "jitter_seconds": jitter_i,
                "allow_unavailable": bool(allow_unavailable),
                "reason": "direct_api_attempt" if allow_unavailable else "capacity_open",
            }
            return create_from_plan(
                plan_path,
                expected_hash,
                approve,
                dry_run,
                receipt_path,
                max_age_hours,
                auth,
                hcloud_bin=hcloud_bin,
                timeout=timeout,
                runner_json=fn_json,
                runner=fn_run,
                allow_unavailable=allow_unavailable,
                _preverified_flight=flight,
                _snipe_meta=snipe_meta,
            )

        failures = flight.get("failures") or []
        non_capacity_failures = [
            f for f in failures if f.get("check") != "location_available"
        ]
        if non_capacity_failures:
            snipe_meta = {
                "polls_completed": poll_idx,
                "max_polls": polls_limit,
                "interval_seconds": interval_i,
                "jitter_seconds": jitter_i,
                "reason": "permanent_preflight_failure",
            }
            receipt = _receipt(
                payload,
                plan_hash,
                "blocked",
                dry_run,
                flight,
                None,
                "Preflight failed on non-capacity check; aborting snipe with no write.",
                None,
                auth,
                snipe_meta=snipe_meta,
            )
            _write_receipt_file(receipt, receipt_path)
            raise PreflightBlocked(
                "Preflight failed on non-capacity check; aborting snipe with no write.",
                flight["checks"],
            )

        if poll_idx < polls_limit:
            delay = float(interval_i) + (
                float(fn_rand(0.0, float(jitter_i))) if jitter_i > 0 else 0.0
            )
            fn_sleep(delay)

    snipe_meta = {
        "polls_completed": polls_limit,
        "max_polls": polls_limit,
        "interval_seconds": interval_i,
        "jitter_seconds": jitter_i,
        "reason": "capacity_unavailable_after_watch",
    }
    receipt = _receipt(
        payload,
        plan_hash,
        "blocked",
        dry_run,
        last_flight,
        None,
        f"Target capacity remained unavailable after {polls_limit} poll(s); no write attempted.",
        None,
        auth,
        snipe_meta=snipe_meta,
    )
    _write_receipt_file(receipt, receipt_path)
    raise PreflightBlocked(
        f"Target capacity remained unavailable after {polls_limit} poll(s); no write attempted.",
        last_flight["checks"] if isinstance(last_flight, dict) else [],
    )
