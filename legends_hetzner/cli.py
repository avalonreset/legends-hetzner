# SPDX-License-Identifier: MIT
"""CLI: python -m legends_hetzner and legends-hetzner entry."""

from __future__ import annotations

import argparse
import json
import sys

from . import PROVISION_SUPPORT, __version__
from . import doctor as doctor_mod
from . import inventory as inv_mod
from . import resources as resources_mod
from . import servers as servers_mod
from .hcloud import HCloudError, resolve_auth

EXIT_GENERAL = 1
EXIT_USAGE = 2
EXIT_PREFLIGHT = 3
EXIT_CREATE = 4
EXIT_AUTH = 5

_CREATE_EPILOG = (
    "Provision support: mocked-write-only until explicit disposable resource "
    "test. One CLI invocation; no client-side retry. Upstream hcloud HTTP "
    "retries (if any) are outside this wrapper."
)


def _code_to_exit(code: str) -> int:
    if code in ("AUTH_MISSING",):
        return EXIT_AUTH
    if code in ("PREFLIGHT_BLOCKED",):
        return EXIT_PREFLIGHT
    if code in ("UNCERTAIN_EXISTS", "UNCERTAIN_MISSING", "UNCERTAIN_UNKNOWN"):
        return EXIT_CREATE
    if code in ("HCLOUD_EXIT", "HCLOUD_BAD_JSON", "TIMEOUT", "HCLOUD_NOT_FOUND",
                "HCLOUD_OS_ERROR", "HCLOUD_DECODE_ERROR"):
        return EXIT_GENERAL
    if code in ("PLAN_INVALID", "PLAN_TAMPERED", "PLAN_STALE", "PLAN_HASH_MISMATCH",
                "PLAN_VERSION", "PLAN_NOT_FOUND", "PLAN_EXISTS", "PLAN_CONTEXT_MISMATCH",
                "NEED_APPROVAL", "AUTH_AMBIGUOUS", "AUTH_LEAK_REFUSED",
                "USERDATA_INVALID", "RECEIPT_EXISTS", "RECEIPT_PATH_INVALID"):
        return EXIT_USAGE
    if code in ("USERDATA_INVALID",):
        return EXIT_USAGE
    return EXIT_GENERAL


def _print_json(obj: dict) -> None:
    print(json.dumps(obj, indent=2))


def _fail(code: str, message: str, detail: str | None = None) -> int:
    sys.stderr.write(f"error [{code}] {message}\n")
    if detail:
        sys.stderr.write(f"{detail[:2000]}\n")
    return _code_to_exit(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="legends-hetzner",
                                     description="Portable hcloud wrapper (stdlib only).")
    parser.add_argument("--context", default=None, help="hcloud named context (bound into plans).")
    parser.add_argument("--timeout", type=int, default=30, help="Per-call timeout 1-120s (default 30).")
    parser.add_argument("--hcloud-bin", default="hcloud", help="hcloud executable (default hcloud).")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    sub = parser.add_subparsers(dest="command")

    doctor_p = sub.add_parser("doctor", help="Offline checks by default; --live adds a read-only probe.")
    doctor_p.add_argument("--live", action="store_true")

    sub.add_parser("inventory", help="List servers as JSON (live read-only).")

    catalog_p = sub.add_parser("catalog", help="List types/locations/images/keys as JSON.")
    catalog_p.add_argument("--kind", default="all",
                           choices=["all", "server-types", "locations", "images", "ssh-keys"])

    server_p = sub.add_parser("server", help="Plan, preflight, and create servers.")
    server_sub = server_p.add_subparsers(dest="server_command", required=True)

    plan_p = server_sub.add_parser("plan", help="Write an immutable reviewed plan file (offline).")
    plan_p.add_argument("--name", required=True)
    plan_p.add_argument("--type", required=True, dest="server_type")
    plan_p.add_argument("--location", required=True)
    plan_p.add_argument("--image", required=True)
    plan_p.add_argument("--ssh-key", action="append", default=[], dest="ssh_keys")
    plan_p.add_argument("--user-data", default=None)
    plan_p.add_argument("--label", action="append", default=[])
    plan_p.add_argument("--out", required=True)

    preflight_p = server_sub.add_parser("preflight", help="Live read-only plan checks (no writes).")
    preflight_p.add_argument("--plan", required=True)
    preflight_p.add_argument("--max-plan-age-hours", type=float, default=24)

    create_p = server_sub.add_parser("create", help="Preflight then one create invocation.",
                                     epilog=_CREATE_EPILOG)
    create_p.add_argument("--plan", required=True)
    create_p.add_argument("--plan-hash", required=True)
    create_p.add_argument("--approve", action="store_true")
    create_p.add_argument("--dry-run", action="store_true")
    create_p.add_argument("--receipt", default=None)
    create_p.add_argument("--max-plan-age-hours", type=float, default=24)

    sub.add_parser("resources", help="Show absolute recipe/pack paths (offline).")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if not args.command:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    timeout = args.timeout
    hcloud_bin = args.hcloud_bin

    if args.command == "doctor":
        if args.live:
            try:
                auth = resolve_auth(args.context)
            except HCloudError as exc:
                return _fail(exc.code, str(exc))
            report = doctor_mod.live(auth, hcloud_bin, timeout)
            _print_json(report)
            if report.get("live_ok"):
                return 0
            codes = {e.get("code") for e in report.get("errors", []) if isinstance(e, dict)}
            if "AUTH_MISSING" in codes:
                return EXIT_AUTH
            return EXIT_GENERAL
        report = doctor_mod.offline(hcloud_bin, timeout)
        _print_json(report)
        if report.get("errors") or not report.get("hcloud_found") or not report.get("python_ok"):
            return EXIT_GENERAL
        return 0

    if args.command == "resources":
        _print_json(resources_mod.resolve())
        return 0

    if args.command in ("inventory", "catalog"):
        try:
            auth = resolve_auth(args.context)
            if args.command == "inventory":
                _print_json(inv_mod.inventory_servers(auth, hcloud_bin, timeout))
            else:
                _print_json(inv_mod.catalog(auth, args.kind, hcloud_bin, timeout))
            return 0
        except ValueError as exc:
            return _fail("PLAN_INVALID", str(exc))
        except HCloudError as exc:
            return _fail(exc.code, str(exc), exc.stderr)

    if args.command == "server":
        if args.server_command == "plan":
            try:
                plan_obj = servers_mod.create_plan(
                    args.name, args.server_type, args.location, args.image,
                    args.ssh_keys, args.user_data, args.label,
                    planned_context=args.context,
                )
                out = servers_mod.write_plan_file(plan_obj, args.out)
                _print_json({"ok": True, "plan_hash": plan_obj["plan_hash"], "out": out,
                             "planned_context": plan_obj["plan"].get("planned_context")})
                return 0
            except HCloudError as exc:
                return _fail(exc.code, str(exc), exc.stderr)
            except OSError as exc:
                return _fail("PLAN_INVALID", f"user-data unreadable: {exc}.")
        if args.server_command == "preflight":
            try:
                auth = resolve_auth(args.context)
                payload, _ = servers_mod.load_plan(args.plan, None, args.max_plan_age_hours)
                result = servers_mod.preflight(payload, auth, hcloud_bin, timeout)
                _print_json(result)
                return 0 if result.get("passed") else EXIT_PREFLIGHT
            except HCloudError as exc:
                return _fail(exc.code, str(exc), getattr(exc, "stderr", None))
        if args.server_command == "create":
            try:
                auth = resolve_auth(args.context)
                receipt = servers_mod.create_from_plan(
                    args.plan, args.plan_hash, args.approve, args.dry_run,
                    args.receipt, args.max_plan_age_hours, auth, hcloud_bin, timeout)
                _print_json(receipt)
                return 0
            except servers_mod.PreflightBlocked as exc:
                sys.stderr.write(f"error [PREFLIGHT_BLOCKED] {exc}\n")
                for check in exc.checks:
                    sys.stderr.write(f" - {check['check']}: {check['detail']}\n")
                return EXIT_PREFLIGHT
            except servers_mod.UncertainError as exc:
                return _fail(exc.code, str(exc))
            except HCloudError as exc:
                return _fail(exc.code, str(exc), getattr(exc, "stderr", None))
    parser.print_help(sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
