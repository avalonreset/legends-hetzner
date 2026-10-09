# SPDX-License-Identifier: MIT
"""Portability and behavior tests for the legends_hetzner runtime.

Method labels used below:
- REAL-SUBPROCESS: local `sys.executable -c` child, no network, no cloud.
- MOCKED: stdlib unittest.mock or fake runner; no subprocess, no network.
- MOCKED-ENV: only os.environ is patched (fake tokens, never real ones).

No test transfers credentials, touches the network, or creates cloud
resources. Auth-missing paths must fail before any subprocess spawns.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOKEN_NAME = "HCLOUD_TOKEN"
FAKE_TOKEN = "qa-fake-token-value-0123456789abcdef"
FAKE_TOKEN_64 = "ab12" * 16  # 64 hex chars, same shape as a real token
NO_BIN = "definitely-not-a-real-binary-qa-0471"


def _spec(name: str):
    try:
        return importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None


HAS_PKG = _spec("legends_hetzner") is not None
HAS_HCLOUD = _spec("legends_hetzner.hcloud") is not None
HAS_DOCTOR = _spec("legends_hetzner.doctor") is not None
HAS_INVENTORY = _spec("legends_hetzner.inventory") is not None
HAS_SERVERS = _spec("legends_hetzner.servers") is not None
HAS_RESOURCES = _spec("legends_hetzner.resources") is not None
HAS_CLI = _spec("legends_hetzner.cli") is not None

if HAS_PKG:
    import legends_hetzner as pkg_mod  # noqa: E402
if HAS_HCLOUD:
    from legends_hetzner import hcloud as hcloud_mod  # noqa: E402
if HAS_DOCTOR:
    from legends_hetzner import doctor as doctor_mod  # noqa: E402
if HAS_INVENTORY:
    from legends_hetzner import inventory as inv_mod  # noqa: E402
if HAS_SERVERS:
    from legends_hetzner import servers as servers_mod  # noqa: E402
if HAS_RESOURCES:
    from legends_hetzner import resources as resources_mod  # noqa: E402

_MISSING = object()


class EnvGuard:
    """Save/restore os.environ entries (MOCKED-ENV). None value unsets."""

    def __init__(self, updates: dict):
        self.updates = dict(updates)
        self.saved: dict = {}

    def __enter__(self):
        for key, value in self.updates.items():
            self.saved[key] = os.environ.get(key, _MISSING)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return self

    def __exit__(self, *exc):
        for key in self.updates:
            old = self.saved[key]
            if old is _MISSING:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        return False


def clean_env(extra: dict | None = None) -> dict:
    """Child env without any real token (fake values only)."""
    env = dict(os.environ)
    env.pop(TOKEN_NAME, None)
    if extra:
        env.update(extra)
    return env


@unittest.skipUnless(HAS_PKG, "legends_hetzner package not landed")
class TestPackageIdentity(unittest.TestCase):
    def test_version_shape(self):
        self.assertRegex(pkg_mod.__version__, r"^\d+\.\d+\.\d+$")
        self.assertEqual(pkg_mod.TOOL, "legends-hetzner")

    def test_contract_consistency(self):
        contract_path = ROOT / "docs" / "CLI-CONTRACT.json"
        if not contract_path.is_file():
            self.skipTest("CLI contract not landed")
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        self.assertEqual(contract["version"], pkg_mod.__version__)
        self.assertEqual(contract["provision_support"],
                         pkg_mod.PROVISION_SUPPORT)


@unittest.skipUnless(HAS_HCLOUD, "hcloud adapter not landed")
class TestAuthMatrix(unittest.TestCase):
    """MOCKED-ENV auth selection (contract: token xor context)."""

    def test_token_only(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
        self.assertEqual(auth.source, "token")
        self.assertTrue(auth.token_present)
        self.assertIsNone(auth.context)

    def test_context_only(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth("qa-ctx")
        self.assertEqual(auth.source, "context")
        self.assertEqual(auth.context, "qa-ctx")
        self.assertFalse(auth.token_present)

    def test_neither_is_none_source(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
        self.assertEqual(auth.source, "none")

    def test_both_is_ambiguous(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                hcloud_mod.resolve_auth("qa-ctx")
        self.assertEqual(ctx.exception.code, "AUTH_AMBIGUOUS")
        self.assertNotIn(FAKE_TOKEN, str(ctx.exception))

    def test_blank_context_ignored(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth("   ")
        self.assertEqual(auth.source, "none")

    def test_require_live_auth(self):
        with EnvGuard({TOKEN_NAME: None}):
            none = hcloud_mod.resolve_auth(None)
        with self.assertRaises(hcloud_mod.HCloudError) as ctx:
            hcloud_mod.require_live_auth(none)
        self.assertEqual(ctx.exception.code, "AUTH_MISSING")
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            hcloud_mod.require_live_auth(hcloud_mod.resolve_auth(None))


@unittest.skipUnless(HAS_HCLOUD, "hcloud adapter not landed")
class TestTimeoutClamp(unittest.TestCase):
    def test_bounds(self):
        clamp = hcloud_mod.clamp_timeout
        self.assertEqual(clamp(None), 30)
        self.assertEqual(clamp(0), 1)
        self.assertEqual(clamp(-5), 1)
        self.assertEqual(clamp(9999), 120)
        self.assertEqual(clamp(30.9), 30)
        self.assertEqual(clamp("nope"), 30)
        self.assertEqual(clamp(45), 45)


@unittest.skipUnless(HAS_HCLOUD, "hcloud adapter not landed")
class TestBuildArgv(unittest.TestCase):
    """MOCKED-ENV argv construction; token values must never enter argv."""

    def test_context_injected(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth("qa-ctx")
            argv = hcloud_mod.build_argv(["server", "list"], auth)
        self.assertEqual(argv, ["hcloud", "--context", "qa-ctx",
                               "server", "list"])

    def test_default_binary(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            self.assertEqual(hcloud_mod.build_argv([], auth, "  ")[0],
                             "hcloud")

    def test_token_value_refused_exact(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                hcloud_mod.build_argv(["x", FAKE_TOKEN], auth)
        self.assertEqual(ctx.exception.code, "AUTH_LEAK_REFUSED")

    def test_token_value_refused_substring(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            with self.assertRaises(hcloud_mod.HCloudError):
                hcloud_mod.build_argv([f"prefix-{FAKE_TOKEN}-suffix"], auth)

    def test_clean_argv_passes(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            argv = hcloud_mod.build_argv(["server", "list", "-o", "json"],
                                         auth)
        self.assertNotIn(FAKE_TOKEN, " ".join(argv))


@unittest.skipUnless(HAS_HCLOUD, "hcloud adapter not landed")
class TestRedact(unittest.TestCase):
    """MOCKED-ENV redaction of token values and token-like patterns."""

    def test_env_token_redacted(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            out = hcloud_mod.redact_text(f"oops {FAKE_TOKEN} here")
        self.assertNotIn(FAKE_TOKEN, out)
        self.assertIn("[REDACTED]", out)

    def test_kv_redacted(self):
        with EnvGuard({TOKEN_NAME: None}):
            out = hcloud_mod.redact_text("token=supersecret-value-1")
        self.assertNotIn("supersecret-value-1", out)

    def test_bare_digest_not_redacted(self):
        # Digest-safe contract: bare hex digests stay printable so
        # plan_hash and user_data_sha256 survive receipts and errors.
        with EnvGuard({TOKEN_NAME: None}):
            out = hcloud_mod.redact_text(f"hash {FAKE_TOKEN_64} end")
        self.assertIn(FAKE_TOKEN_64, out)

    def test_known_64hex_token_redacted(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN_64}):
            out = hcloud_mod.redact_text(f"leak {FAKE_TOKEN_64} end")
        self.assertNotIn(FAKE_TOKEN_64, out)

    def test_plain_text_untouched(self):
        with EnvGuard({TOKEN_NAME: None}):
            self.assertEqual(hcloud_mod.redact_text("hcloud 1.70.1"),
                             "hcloud 1.70.1")
            self.assertEqual(hcloud_mod.redact_text(""), "")

    def test_redact_obj_nested(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            out = hcloud_mod.redact_obj(
                {"a": [FAKE_TOKEN, 1], "b": {"c": f"x {FAKE_TOKEN}"}})
        blob = json.dumps(out)
        self.assertNotIn(FAKE_TOKEN, blob)

    def test_sha256_digest_preserved(self):
        digest = "sha256:" + "c3" * 32
        with EnvGuard({TOKEN_NAME: None}):
            out = hcloud_mod.redact_text(f"plan {digest} ok")
        self.assertIn(digest, out)

    def test_bearer_and_json_token_redacted(self):
        with EnvGuard({TOKEN_NAME: None}):
            out = hcloud_mod.redact_text(
                "Authorization: Bearer abcdef1234567890")
        self.assertNotIn("abcdef1234567890", out)
        with EnvGuard({TOKEN_NAME: None}):
            out = hcloud_mod.redact_text('{"api_token": "zzz-top-secret"}')
        self.assertNotIn("zzz-top-secret", out)

    def test_sensitive_keyed_value_redacted(self):
        with EnvGuard({TOKEN_NAME: None}):
            out = hcloud_mod.redact_obj({"api_token": "zzz-1", "name": "s"})
        self.assertEqual(out["api_token"], "[REDACTED]")
        self.assertEqual(out["name"], "s")


@unittest.skipUnless(HAS_HCLOUD, "hcloud adapter not landed")
class TestRunRealSubprocess(unittest.TestCase):
    """REAL-SUBPROCESS via sys.executable stubs (no network, no cloud)."""

    def test_missing_binary(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                hcloud_mod.run(["version"], auth, hcloud_bin=NO_BIN)
        self.assertEqual(ctx.exception.code, "HCLOUD_NOT_FOUND")

    def test_stdout_returned(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            out = hcloud_mod.run(
                ["-c", "print('qa-stdout-7')"], auth, timeout=15,
                hcloud_bin=sys.executable)
        self.assertIn("qa-stdout-7", out)

    def test_nonzero_exit_sanitized(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            # Stub reads the token from its own env; argv carries no value.
            code = ("import os, sys; sys.stderr.write('boom ' + "
                    "os.environ.get(\"" + TOKEN_NAME + "\", \"\")); "
                    "sys.exit(3)")
            with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                hcloud_mod.run(["-c", code], auth, timeout=15,
                               hcloud_bin=sys.executable)
        self.assertEqual(ctx.exception.code, "HCLOUD_EXIT")
        self.assertEqual(ctx.exception.exit_code, 3)
        blob = (ctx.exception.stderr or "") + str(ctx.exception)
        self.assertNotIn(FAKE_TOKEN, blob)

    def test_timeout(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                hcloud_mod.run(["-c", "import time; time.sleep(30)"],
                               auth, timeout=1,
                               hcloud_bin=sys.executable)
        self.assertEqual(ctx.exception.code, "TIMEOUT")

    def test_run_json_good(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            data = hcloud_mod.run_json(
                ["-c", "print('{\"k\": [1, 2]}')"], auth, timeout=15,
                hcloud_bin=sys.executable)
        self.assertEqual(data, {"k": [1, 2]})

    def test_run_json_bad(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                hcloud_mod.run_json(["-c", "print('not json')"], auth,
                                    timeout=15,
                                    hcloud_bin=sys.executable)
        self.assertEqual(ctx.exception.code, "HCLOUD_BAD_JSON")

    def test_token_reaches_child(self):
        # REAL-SUBPROCESS: token auth keeps the value in the child env.
        probe = ("import os; print('HAS' if os.environ.get("
                 f'"{TOKEN_NAME}") else "NONE")')
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            out = hcloud_mod.run(["-c", probe], auth, timeout=15,
                                 hcloud_bin=sys.executable)
        self.assertIn("HAS", out)

    def test_context_child_env_strips_token(self):
        # Unit-level: --context argv cannot run through a Python stub,
        # so the exact child-env builder run() uses is tested directly.
        ctx_auth = hcloud_mod.Auth(context="qa-ctx", token_present=False,
                                   source="context")
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN,
                       "HCLOUD_ENDPOINT": "https://evil.invalid/",
                       "HCLOUD_DEBUG": "1"}):
            env = hcloud_mod._child_env(ctx_auth)
        self.assertNotIn(TOKEN_NAME, env)
        self.assertNotIn("HCLOUD_ENDPOINT", env)
        self.assertNotIn("HCLOUD_DEBUG", env)
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            kept = hcloud_mod._child_env(hcloud_mod.resolve_auth(None))
        self.assertEqual(kept[TOKEN_NAME], FAKE_TOKEN)


@unittest.skipUnless(HAS_HCLOUD, "hcloud adapter not landed")
class TestWhichHcloud(unittest.TestCase):
    def test_missing_returns_none(self):
        self.assertIsNone(hcloud_mod.which_hcloud(NO_BIN))

    def test_explicit_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "hcloud"
            target.write_text("x", encoding="utf-8")
            self.assertEqual(hcloud_mod.which_hcloud(str(target)),
                             str(target))
            self.assertIsNone(
                hcloud_mod.which_hcloud(str(Path(tmp) / "nope")))


@unittest.skipUnless(HAS_DOCTOR, "doctor not landed")
class TestDoctorOffline(unittest.TestCase):
    def test_missing_binary(self):
        with EnvGuard({TOKEN_NAME: None}):
            report = doctor_mod.offline(hcloud_bin=NO_BIN, timeout=5)
        self.assertEqual(report["mode"], "offline")
        self.assertFalse(report["hcloud_found"])
        self.assertTrue(report["python_ok"])
        self.assertEqual(report["version"], pkg_mod.__version__)
        codes = [e["code"] for e in report["errors"]]
        self.assertIn("HCLOUD_NOT_FOUND", codes)

    def test_version_captured_mocked(self):
        # MOCKED subprocess layer; parsing behavior is real.
        with EnvGuard({TOKEN_NAME: None}), \
                mock.patch.object(doctor_mod, "which_hcloud",
                                  return_value="/qa/hcloud"), \
                mock.patch.object(doctor_mod, "run",
                                  return_value="hcloud 1.70.1\n"):
            report = doctor_mod.offline(hcloud_bin="/qa/hcloud", timeout=5)
        self.assertTrue(report["hcloud_found"])
        self.assertTrue(report["hcloud_version"].startswith("hcloud "))
        self.assertEqual(report["errors"], [])

    def test_live_without_auth_spawns_nothing(self):
        # Live probe with no auth reports live_ok False and must not
        # spawn any subprocess (both run entry points would explode).
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            with mock.patch.object(doctor_mod, "run",
                                   side_effect=AssertionError("run")), \
                    mock.patch.object(doctor_mod, "run_json",
                                      side_effect=AssertionError("run_json")):
                report = doctor_mod.live(auth, hcloud_bin=NO_BIN,
                                         timeout=5)
        self.assertEqual(report["mode"], "live")
        self.assertFalse(report["live_ok"])
        codes = [e["code"] for e in report["errors"]]
        self.assertIn("AUTH_MISSING", codes)


@unittest.skipUnless(HAS_INVENTORY, "inventory not landed")
class TestInventoryAuth(unittest.TestCase):
    """Auth is enforced before any subprocess (MOCKED explode guards)."""

    def test_servers_no_auth(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            with mock.patch.object(inv_mod, "run_json",
                                   side_effect=AssertionError("spawn")):
                with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                    inv_mod.inventory_servers(auth, hcloud_bin=NO_BIN)
        self.assertEqual(ctx.exception.code, "AUTH_MISSING")

    def test_catalog_no_auth(self):
        with EnvGuard({TOKEN_NAME: None}):
            auth = hcloud_mod.resolve_auth(None)
            with mock.patch.object(inv_mod, "run_json",
                                   side_effect=AssertionError("spawn")):
                with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                    inv_mod.catalog(auth, hcloud_bin=NO_BIN)
        self.assertEqual(ctx.exception.code, "AUTH_MISSING")

    def test_unknown_kind_before_subprocess(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            with mock.patch.object(inv_mod, "run_json",
                                   side_effect=AssertionError("spawn")):
                with self.assertRaises(ValueError):
                    inv_mod.catalog(auth, kind="bogus-qa",
                                    hcloud_bin=NO_BIN)


@unittest.skipUnless(HAS_INVENTORY, "inventory not landed")
class TestInventoryParsing(unittest.TestCase):
    """MOCKED run_json; list shaping and redaction are real."""

    def test_servers_shapes(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            with mock.patch.object(inv_mod, "run_json",
                                   return_value=[{"name": "s1"}]):
                out = inv_mod.inventory_servers(auth, hcloud_bin=NO_BIN)
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["servers"], [{"name": "s1"}])
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            with mock.patch.object(inv_mod, "run_json",
                                   return_value={"servers": []}):
                out = inv_mod.inventory_servers(auth, hcloud_bin=NO_BIN)
        self.assertEqual(out, {"servers": [], "count": 0})

    def test_servers_redacted(self):
        payload = [{"name": f"qa {FAKE_TOKEN}"}]
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            with mock.patch.object(inv_mod, "run_json",
                                   return_value=payload):
                out = inv_mod.inventory_servers(auth, hcloud_bin=NO_BIN)
        self.assertNotIn(FAKE_TOKEN, json.dumps(out))

    def test_catalog_all_and_single(self):
        with EnvGuard({TOKEN_NAME: FAKE_TOKEN}):
            auth = hcloud_mod.resolve_auth(None)
            with mock.patch.object(inv_mod, "run_json", return_value=[]):
                everything = inv_mod.catalog(auth, hcloud_bin=NO_BIN)
                single = inv_mod.catalog(auth, kind="locations",
                                         hcloud_bin=NO_BIN)
        self.assertEqual(set(everything),
                         {"server_types", "locations", "images", "ssh_keys"})
        self.assertEqual(single["kind"], "locations")
        self.assertEqual(single["count"], 0)


def _independent_plan_hash(payload: dict) -> str:
    """Recompute per the CLI contract (not via servers.plan_hash_of)."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


@unittest.skipUnless(HAS_SERVERS, "servers module not landed")
class TestPlanOffline(unittest.TestCase):
    def test_create_plan_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = servers_mod.create_plan(
                "qa-plan-1", "cax11", "hel1", "ubuntu-24.04",
                ["key-b", "key-a", "key-a"], planned_context=" qa-ctx ")
        payload = plan["plan"]
        self.assertEqual(plan["plan_hash"],
                         _independent_plan_hash(payload))
        self.assertEqual(payload["ssh_keys"], ["key-a", "key-b"])
        self.assertEqual(payload["planned_context"], "qa-ctx")
        self.assertEqual(payload["version"], 1)

    def test_create_plan_requires_ssh_key(self):
        with self.assertRaises(servers_mod.PlanError) as ctx:
            servers_mod.create_plan("qa-plan-1", "cax11", "hel1",
                                    "ubuntu-24.04", [])
        self.assertEqual(ctx.exception.code, "PLAN_INVALID")

    def test_create_plan_rejects_bad_name_and_label(self):
        with self.assertRaises(servers_mod.PlanError):
            servers_mod.create_plan("bad name!", "cax11", "hel1",
                                    "ubuntu-24.04", ["k"])
        with self.assertRaises(servers_mod.PlanError):
            servers_mod.create_plan("qa-ok", "cax11", "hel1", "ubuntu-24.04",
                                    ["k"], labels=["no-equals"])

    def test_user_data_roundtrip(self):
        raw = b"#cloud-config\nruncmd: [echo qa]\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ud.yaml"
            src.write_bytes(raw)
            plan = servers_mod.create_plan(
                "qa-ud", "cax11", "hel1", "ubuntu-24.04", ["k"],
                user_data_path=str(src))
        payload = plan["plan"]
        expect = "sha256:" + hashlib.sha256(raw).hexdigest()
        self.assertEqual(payload["user_data_sha256"], expect)
        self.assertEqual(plan["plan_hash"],
                         _independent_plan_hash(payload))

    def test_user_data_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.txt"
            bad.write_bytes(b"no magic header\n")
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.create_plan("qa-ud", "cax11", "hel1",
                                        "ubuntu-24.04", ["k"],
                                        user_data_path=str(bad))
            self.assertEqual(ctx.exception.code, "USERDATA_INVALID")
            big = Path(tmp) / "big.txt"
            big.write_bytes(b"#!/bin/sh\n" + b"x" * 32768)
            with self.assertRaises(servers_mod.PlanError):
                servers_mod.create_plan("qa-ud", "cax11", "hel1",
                                        "ubuntu-24.04", ["k"],
                                        user_data_path=str(big))

    def test_write_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "sub" / "plan.json")
            plan = servers_mod.create_plan("qa-w", "cax11", "hel1",
                                           "ubuntu-24.04", ["k"])
            servers_mod.write_plan_file(plan, out)
            self.assertTrue(Path(out).is_file())
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.write_plan_file(plan, out)
            self.assertEqual(ctx.exception.code, "PLAN_EXISTS")

    def _written_plan(self, tmp: str) -> tuple[str, dict]:
        plan = servers_mod.create_plan("qa-load", "cax11", "hel1",
                                       "ubuntu-24.04", ["k"])
        out = str(Path(tmp) / "plan.json")
        servers_mod.write_plan_file(plan, out)
        return out, plan

    def test_load_roundtrip_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, plan = self._written_plan(tmp)
            payload, embedded = servers_mod.load_plan(out)
            self.assertEqual(embedded, plan["plan_hash"])
            obj = json.loads(Path(out).read_text(encoding="utf-8"))
            obj["plan"]["name"] = "qa-tampered"
            Path(out).write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.load_plan(out)
            self.assertEqual(ctx.exception.code, "PLAN_TAMPERED")

    def test_load_hash_format_and_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, plan = self._written_plan(tmp)
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.load_plan(out, "not-a-hash")
            self.assertEqual(ctx.exception.code, "PLAN_HASH_MISMATCH")
            wrong = "sha256:" + "0" * 64
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.load_plan(out, wrong)
            self.assertEqual(ctx.exception.code, "PLAN_HASH_MISMATCH")
            _payload, embedded = servers_mod.load_plan(out,
                                                       plan["plan_hash"])
            self.assertEqual(embedded, plan["plan_hash"])

    def test_load_stale_and_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _plan = self._written_plan(tmp)
            obj = json.loads(Path(out).read_text(encoding="utf-8"))
            obj["plan"]["created_at"] = "2020-01-01T00:00:00Z"
            obj["plan_hash"] = _independent_plan_hash(obj["plan"])
            Path(out).write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.load_plan(out)
            self.assertEqual(ctx.exception.code, "PLAN_STALE")
            obj["plan"]["created_at"] = "2999-01-01T00:00:00Z"
            obj["plan_hash"] = _independent_plan_hash(obj["plan"])
            Path(out).write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.load_plan(out)
            self.assertEqual(ctx.exception.code, "PLAN_INVALID")

    def test_context_binding_matrix(self):
        tok = hcloud_mod.Auth(context=None, token_present=True,
                              source="token")
        ctx_a = hcloud_mod.Auth(context="qa-a", token_present=False,
                                source="context")
        ctx_b = hcloud_mod.Auth(context="qa-b", token_present=False,
                                source="context")
        servers_mod.enforce_planned_context({"planned_context": "qa-a"},
                                            ctx_a)
        servers_mod.enforce_planned_context({"planned_context": None},
                                            tok)
        with self.assertRaises(servers_mod.PlanError) as ctx:
            servers_mod.enforce_planned_context({"planned_context": "qa-a"},
                                                ctx_b)
        self.assertEqual(ctx.exception.code, "PLAN_CONTEXT_MISMATCH")
        with self.assertRaises(servers_mod.PlanError):
            servers_mod.enforce_planned_context({"planned_context": None},
                                                ctx_a)

    def test_receipt_path_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "r" / "receipt.json"
            servers_mod.validate_receipt_path(str(target))
            leftovers = list(Path(tmp).rglob(".lh-receipt-probe-*"))
            self.assertEqual(leftovers, [])
            target.write_text("x", encoding="utf-8")
            with self.assertRaises(servers_mod.CreateError) as ctx:
                servers_mod.validate_receipt_path(str(target))
            self.assertEqual(ctx.exception.code, "RECEIPT_EXISTS")


def _canned_preflight_pass(shape="new"):
    """MOCKED hcloud list payloads shaped like 1.61 or newer output."""
    if shape == "161":
        locations = [{"id": 1, "name": "hel1"}]
    else:
        locations = [{"location": "hel1", "available": True}]
    data = {
        "server": [],
        "server-type": [{"id": 22, "name": "cax11", "architecture": "arm",
                        "locations": locations}],
        "location": [{"id": 1, "name": "hel1"}],
        "image": [{"id": 1, "name": "ubuntu-24.04", "architecture": "arm"}],
        "ssh-key": [{"id": 1, "name": "k"}],
    }

    def fake(argv, auth, timeout=None, hcloud_bin="hcloud"):
        return data[argv[0]]

    return fake


@unittest.skipUnless(HAS_SERVERS, "servers module not landed")
class TestPreflightMocked(unittest.TestCase):
    """MOCKED runner_json; check logic across hcloud output shapes."""

    def _payload(self):
        return servers_mod.create_plan("qa-pf", "cax11", "hel1",
                                       "ubuntu-24.04", ["k"])["plan"]

    def _auth(self):
        return hcloud_mod.Auth(context=None, token_present=True,
                               source="token")

    def test_all_pass_new_shape(self):
        out = servers_mod.preflight(self._payload(), self._auth(),
                                    NO_BIN, 5,
                                    runner_json=_canned_preflight_pass())
        self.assertTrue(out["passed"], out["failures"])
        self.assertEqual(out["failures"], [])

    def test_all_pass_161_shape(self):
        out = servers_mod.preflight(self._payload(), self._auth(),
                                    NO_BIN, 5,
                                    runner_json=_canned_preflight_pass("161"))
        self.assertTrue(out["passed"], out["failures"])

    def test_name_taken_blocks(self):
        def fake(argv, auth, timeout=None, hcloud_bin="hcloud"):
            if argv[0] == "server":
                return [{"name": "qa-pf"}]
            return _canned_preflight_pass()(argv, auth, timeout,
                                            hcloud_bin)

        out = servers_mod.preflight(self._payload(), self._auth(),
                                    NO_BIN, 5, runner_json=fake)
        self.assertFalse(out["passed"])
        names = [c["check"] for c in out["failures"]]
        self.assertIn("name_available", names)

    def test_arch_mismatch_blocks(self):
        def fake(argv, auth, timeout=None, hcloud_bin="hcloud"):
            if argv[0] == "image":
                return [{"id": 9, "name": "ubuntu-24.04",
                         "architecture": "x86"}]
            return _canned_preflight_pass()(argv, auth, timeout,
                                            hcloud_bin)

        out = servers_mod.preflight(self._payload(), self._auth(),
                                    NO_BIN, 5, runner_json=fake)
        names = [c["check"] for c in out["failures"]]
        self.assertIn("arch_compatible", names)

    def test_missing_key_and_deprecated(self):
        def fake(argv, auth, timeout=None, hcloud_bin="hcloud"):
            if argv[0] == "ssh-key":
                return [{"name": "other"}]
            if argv[0] == "image":
                return [{"id": 1, "name": "ubuntu-24.04",
                         "architecture": "arm",
                         "deprecation": {"announced": "x"}}]
            return _canned_preflight_pass()(argv, auth, timeout,
                                            hcloud_bin)

        out = servers_mod.preflight(self._payload(), self._auth(),
                                    NO_BIN, 5, runner_json=fake)
        names = [c["check"] for c in out["failures"]]
        self.assertIn("ssh_keys_exist", names)
        self.assertIn("image_not_deprecated", names)

    def test_no_auth_before_runner(self):
        def explode(argv, auth, timeout=None, hcloud_bin="hcloud"):
            raise AssertionError("must not call runner")

        none = hcloud_mod.Auth(context=None, token_present=False,
                               source="none")
        with self.assertRaises(hcloud_mod.HCloudError) as ctx:
            servers_mod.preflight(self._payload(), none, NO_BIN, 5,
                                  runner_json=explode)
        self.assertEqual(ctx.exception.code, "AUTH_MISSING")

    def test_context_mismatch_before_runner(self):
        def explode(argv, auth, timeout=None, hcloud_bin="hcloud"):
            raise AssertionError("must not call runner")

        payload = servers_mod.create_plan(
            "qa-ctx", "cax11", "hel1", "ubuntu-24.04", ["k"],
            planned_context="qa-a")["plan"]
        other = hcloud_mod.Auth(context="qa-b", token_present=False,
                                source="context")
        with self.assertRaises(servers_mod.PlanError) as ctx:
            servers_mod.preflight(payload, other, NO_BIN, 5,
                                  runner_json=explode)
        self.assertEqual(ctx.exception.code, "PLAN_CONTEXT_MISMATCH")


@unittest.skipUnless(HAS_SERVERS, "servers module not landed")
class TestCreateMocked(unittest.TestCase):
    """MOCKED runners; approval/hash/context/receipt logic is real."""

    def _plan_file(self, tmp: str) -> tuple[str, str]:
        plan = servers_mod.create_plan("qa-create", "cax11", "hel1",
                                       "ubuntu-24.04", ["k"])
        out = str(Path(tmp) / "plan.json")
        servers_mod.write_plan_file(plan, out)
        return out, plan["plan_hash"]

    def _auth(self):
        return hcloud_mod.Auth(context=None, token_present=True,
                               source="token")

    def test_empty_hash_and_no_approve(self):
        def explode(*a, **k):
            raise AssertionError("must stay local")

        with tempfile.TemporaryDirectory() as tmp:
            out, _ = self._plan_file(tmp)
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.create_from_plan(out, "", True, True, None,
                                             24, self._auth(), NO_BIN, 5,
                                             runner_json=explode,
                                             runner=explode)
            self.assertEqual(ctx.exception.code, "PLAN_HASH_MISMATCH")
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.create_from_plan(
                    out, "sha256:" + "0" * 64, False, True, None, 24,
                    self._auth(), NO_BIN, 5, runner_json=explode,
                    runner=explode)
            # Hash is verified at load, before the approval gate.
            self.assertEqual(ctx.exception.code, "PLAN_HASH_MISMATCH")

    def test_approve_and_auth_gates(self):
        def explode(*a, **k):
            raise AssertionError("must stay local")

        with tempfile.TemporaryDirectory() as tmp:
            out, plan_hash = self._plan_file(tmp)
            with self.assertRaises(servers_mod.PlanError) as ctx:
                servers_mod.create_from_plan(out, plan_hash, False, True,
                                             None, 24, self._auth(),
                                             NO_BIN, 5, runner_json=explode,
                                             runner=explode)
            self.assertEqual(ctx.exception.code, "NEED_APPROVAL")
            none = hcloud_mod.Auth(context=None, token_present=False,
                                   source="none")
            with self.assertRaises(hcloud_mod.HCloudError) as ctx:
                servers_mod.create_from_plan(out, plan_hash, True, True,
                                             None, 24, none, NO_BIN, 5,
                                             runner_json=explode,
                                             runner=explode)
            self.assertEqual(ctx.exception.code, "AUTH_MISSING")

    def test_dry_run_never_calls_runner(self):
        def explode_runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
            raise AssertionError("dry-run must not invoke create")

        with tempfile.TemporaryDirectory() as tmp:
            out, plan_hash = self._plan_file(tmp)
            receipt = servers_mod.create_from_plan(
                out, plan_hash, True, True, None, 24, self._auth(),
                NO_BIN, 5, runner_json=_canned_preflight_pass(),
                runner=explode_runner)
        self.assertEqual(receipt["status"], "dry_run")
        self.assertTrue(receipt["dry_run"])
        self.assertTrue(receipt["preflight"]["passed"])
        self.assertEqual(receipt["plan_hash"], plan_hash)

    def test_blocked_preflight_writes_receipt(self):
        def fake(argv, auth, timeout=None, hcloud_bin="hcloud"):
            if argv[0] == "server":
                return [{"name": "qa-create"}]
            return _canned_preflight_pass()(argv, auth, timeout,
                                            hcloud_bin)

        def explode_runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
            raise AssertionError("blocked must not invoke create")

        with tempfile.TemporaryDirectory() as tmp:
            out, plan_hash = self._plan_file(tmp)
            receipt_path = str(Path(tmp) / "receipt.json")
            with self.assertRaises(servers_mod.PreflightBlocked):
                servers_mod.create_from_plan(
                    out, plan_hash, True, False, receipt_path, 24,
                    self._auth(), NO_BIN, 5, runner_json=fake,
                    runner=explode_runner)
            saved = json.loads(Path(receipt_path).read_text(
                encoding="utf-8"))
        self.assertEqual(saved["status"], "blocked")
        self.assertEqual(saved["plan_hash"], plan_hash)

    def test_created_single_invocation(self):
        calls: list[list[str]] = []
        describe = {"id": 7, "name": "qa-create",
                    "server_type": {"name": "cax11"},
                    "location": {"name": "hel1"},
                    "image": {"name": "ubuntu-24.04"}}

        def fake_json(argv, auth, timeout=None, hcloud_bin="hcloud"):
            if argv[0] == "server" and argv[1] == "describe":
                return dict(describe)
            return _canned_preflight_pass()(argv, auth, timeout,
                                            hcloud_bin)

        def fake_run(argv, auth, timeout=None, hcloud_bin="hcloud"):
            calls.append(list(argv))
            self.assertEqual(argv[:2], ["server", "create"])
            self.assertIn("--user-data-from-file", argv, argv)
            return json.dumps({"server": {"id": 7}})

        with tempfile.TemporaryDirectory() as tmp:
            ud = Path(tmp) / "ud.txt"
            ud.write_bytes(b"#!/bin/sh\necho qa\n")
            plan = servers_mod.create_plan(
                "qa-create", "cax11", "hel1", "ubuntu-24.04", ["k"],
                user_data_path=str(ud))
            out = str(Path(tmp) / "plan.json")
            servers_mod.write_plan_file(plan, out)
            receipt = servers_mod.create_from_plan(
                out, plan["plan_hash"], True, False, None, 24,
                self._auth(), NO_BIN, 5, runner_json=fake_json,
                runner=fake_run)
        self.assertEqual(receipt["status"], "created")
        self.assertEqual(len(calls), 1)
        self.assertEqual(receipt["plan_hash"], plan["plan_hash"])
        self.assertTrue(receipt["readback"]["found"])

    def test_timeout_is_uncertain_never_success(self):
        def fake_json(argv, auth, timeout=None, hcloud_bin="hcloud"):
            if argv[0] == "server" and argv[1] == "describe":
                return {}
            return _canned_preflight_pass()(argv, auth, timeout,
                                            hcloud_bin)

        def fake_run(argv, auth, timeout=None, hcloud_bin="hcloud"):
            raise hcloud_mod.HCloudError("TIMEOUT", "timed out")

        with tempfile.TemporaryDirectory() as tmp:
            out, plan_hash = self._plan_file(tmp)
            with self.assertRaises(servers_mod.UncertainError) as ctx:
                servers_mod.create_from_plan(
                    out, plan_hash, True, False, None, 24, self._auth(),
                    NO_BIN, 5, runner_json=fake_json, runner=fake_run)
        self.assertEqual(ctx.exception.code, "UNCERTAIN_UNKNOWN")


@unittest.skipUnless(HAS_RESOURCES, "resources module not landed")
class TestResources(unittest.TestCase):
    def test_resolve_shape_matches_filesystem(self):
        info = resources_mod.resolve()
        for key in ("version", "root", "recipe", "recipe_exists",
                    "pack_dir", "pack_exists", "pack_files",
                    "cloud_init_dir", "skills_cto_legends", "source"):
            self.assertIn(key, info)
        self.assertEqual(info["version"], pkg_mod.__version__)
        self.assertEqual(info["source"], "checkout")
        for key in ("root", "recipe", "pack_dir", "cloud_init_dir",
                    "skills_cto_legends"):
            self.assertTrue(Path(info[key]).is_absolute(), key)
        self.assertEqual(info["recipe_exists"],
                         Path(info["recipe"]).is_file())
        self.assertTrue(info["recipe_exists"])
        self.assertTrue(info["pack_exists"])
        self.assertGreater(len(info["pack_files"]), 0)
        for entry in info["pack_files"]:
            self.assertTrue(Path(entry).is_file(), entry)


def _run_cli(*args: str, token: str | None = None,
             timeout: int = 60) -> subprocess.CompletedProcess:
    env = clean_env({TOKEN_NAME: token} if token else None)
    return subprocess.run(
        [sys.executable, "-m", "legends_hetzner", *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        timeout=timeout)


@unittest.skipUnless(HAS_CLI, "CLI not landed")
class TestCliOffline(unittest.TestCase):
    """REAL-SUBPROCESS CLI (python -m); no network, no cloud writes."""

    def test_version(self):
        proc = _run_cli("--version")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), pkg_mod.__version__)

    def test_no_command_is_usage(self):
        proc = _run_cli()
        self.assertEqual(proc.returncode, 2)

    def test_doctor_offline(self):
        proc = _run_cli("--hcloud-bin", NO_BIN, "doctor")
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual(report["mode"], "offline")
        self.assertTrue(report["python_ok"])
        self.assertFalse(report["hcloud_found"])

    def test_doctor_offline_real_binary(self):
        import shutil
        if shutil.which("hcloud") is None:
            self.skipTest("no hcloud on PATH")
        proc = _run_cli("doctor")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["hcloud_found"])
        self.assertTrue(report["hcloud_version"].startswith("hcloud "))

    def test_doctor_live_probe_reports_auth(self):
        proc = _run_cli("--hcloud-bin", NO_BIN, "doctor", "--live")
        self.assertEqual(proc.returncode, 5)
        report = json.loads(proc.stdout)
        self.assertFalse(report["live_ok"])
        codes = [e["code"] for e in report["errors"]]
        self.assertIn("AUTH_MISSING", codes)

    def test_resources(self):
        proc = _run_cli("resources")
        self.assertEqual(proc.returncode, 0)
        info = json.loads(proc.stdout)
        self.assertTrue(info["recipe_exists"])
        self.assertTrue(info["pack_exists"])

    def test_inventory_and_catalog_need_auth(self):
        proc = _run_cli("inventory")
        self.assertEqual(proc.returncode, 5)
        self.assertIn("AUTH_MISSING", proc.stderr)
        proc = _run_cli("catalog", "--kind", "locations")
        self.assertEqual(proc.returncode, 5)
        proc = _run_cli("catalog", "--kind", "bogus-qa")
        self.assertEqual(proc.returncode, 2)

    def test_inventory_missing_binary_is_local(self):
        proc = _run_cli("--hcloud-bin", NO_BIN, "inventory",
                        token=FAKE_TOKEN)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("HCLOUD_NOT_FOUND", proc.stderr)

    def _plan_via_cli(self, tmp: str, name: str = "qa-cli-1",
                      extra: list[str] | None = None):
        out = str(Path(tmp) / f"{name}.json")
        args = ["server", "plan", "--name", name, "--type", "cax11",
                "--location", "hel1", "--image", "ubuntu-24.04",
                "--ssh-key", "key-b", "--ssh-key", "key-a",
                "--out", out]
        proc = _run_cli(*args, *(extra or []))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        obj = json.loads(Path(out).read_text(encoding="utf-8"))
        return out, result, obj

    def test_plan_golden_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, result, obj = self._plan_via_cli(tmp)
        self.assertTrue(result["ok"])
        self.assertEqual(result["plan_hash"],
                         _independent_plan_hash(obj["plan"]))
        self.assertEqual(obj["plan"]["ssh_keys"], ["key-a", "key-b"])
        self.assertEqual(result["out"], out)

    def test_plan_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _, _ = self._plan_via_cli(tmp)
            proc = _run_cli("server", "plan", "--name", "qa-cli-1",
                            "--type", "cax11", "--location", "hel1",
                            "--image", "ubuntu-24.04", "--ssh-key", "k",
                            "--out", out)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("PLAN_EXISTS", proc.stderr)

    def test_plan_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run_cli("server", "plan", "--name", "qa-nov", "--type",
                            "cax11", "--location", "hel1", "--image",
                            "ubuntu-24.04",
                            "--out", str(Path(tmp) / "x.json"))
            self.assertEqual(proc.returncode, 2)
            bad = Path(tmp) / "bad.txt"
            bad.write_bytes(b"nope\n")
            proc = _run_cli("server", "plan", "--name", "qa-bud", "--type",
                            "cax11", "--location", "hel1", "--image",
                            "ubuntu-24.04", "--ssh-key", "k", "--user-data",
                            str(bad), "--out", str(Path(tmp) / "y.json"))
            self.assertEqual(proc.returncode, 2)
            self.assertIn("USERDATA_INVALID", proc.stderr)

    def test_preflight_local_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "nope.json")
            proc = _run_cli("server", "preflight", "--plan", missing)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("PLAN_NOT_FOUND", proc.stderr)
            out, _, _ = self._plan_via_cli(tmp, name="qa-pf-cli")
            proc = _run_cli("server", "preflight", "--plan", out)
            self.assertEqual(proc.returncode, 5)
            self.assertIn("AUTH_MISSING", proc.stderr)
            proc = _run_cli("--hcloud-bin", NO_BIN, "server",
                            "preflight", "--plan", out, token=FAKE_TOKEN)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("HCLOUD_NOT_FOUND", proc.stderr)

    def test_create_local_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "nope.json")
            proc = _run_cli("server", "create", "--plan", missing,
                            "--plan-hash", "sha256:" + "0" * 64,
                            "--approve")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("PLAN_NOT_FOUND", proc.stderr)
            out, result, _obj = self._plan_via_cli(tmp, name="qa-cr-cli")
            proc = _run_cli("server", "create", "--plan", out,
                            "--plan-hash", "sha256:" + "0" * 64,
                            "--approve")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("PLAN_HASH_MISMATCH", proc.stderr)
            proc = _run_cli("server", "create", "--plan", out,
                            "--plan-hash", result["plan_hash"])
            self.assertEqual(proc.returncode, 2)
            self.assertIn("NEED_APPROVAL", proc.stderr)
            proc = _run_cli("server", "create", "--plan", out,
                            "--plan-hash", result["plan_hash"], "--approve")
            self.assertEqual(proc.returncode, 5)
            self.assertIn("AUTH_MISSING", proc.stderr)
            proc = _run_cli("--hcloud-bin", NO_BIN, "server",
                            "create", "--plan", out,
                            "--plan-hash", result["plan_hash"], "--approve",
                            token=FAKE_TOKEN)
            self.assertEqual(proc.returncode, 3)
            self.assertIn("PREFLIGHT_BLOCKED", proc.stderr)
