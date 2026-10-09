# SPDX-License-Identifier: MIT
"""Mocked tests: hcloud argv adapter safety, auth, errors, redaction.

No live hcloud calls; subprocess.run is mocked except one local timeout
fixture that runs a sleeping Python snippet (no provider, no writes).
"""

import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from legends_hetzner import hcloud as H


def _auth_none():
    return H.Auth(context=None, token_present=False, source="none")


def _auth_token():
    return H.Auth(context=None, token_present=True, source="token")


def _auth_ctx(name="proj-a"):
    return H.Auth(context=name, token_present=False, source="context")


class SubprocessSafetyTest(unittest.TestCase):
    def test_argv_list_no_shell_and_context_first(self):
        with patch.object(H.subprocess, "run") as m:
            m.return_value = subprocess.CompletedProcess(
                args=["hcloud"], returncode=0, stdout="[]", stderr="")
            H.run(["server", "list", "-o", "json"], _auth_ctx("team"),
                  timeout=12, hcloud_bin="hcloud")
            _, kwargs = m.call_args
            self.assertFalse(kwargs.get("shell"))
            argv = m.call_args.args[0]
            self.assertIsInstance(argv, list)
            self.assertEqual(argv[:3], ["hcloud", "--context", "team"])
            self.assertEqual(kwargs.get("timeout"), 12)

    def test_timeout_clamped_bounded(self):
        self.assertEqual(H.clamp_timeout(0), 1)
        self.assertEqual(H.clamp_timeout(9999), 120)
        self.assertEqual(H.clamp_timeout(None), 30)

    def test_real_timeout_fixture_shape(self):
        # Real local timeout (sleep snippet); proves TimeoutExpired handling
        # works against actual subprocess output attributes.
        with self.assertRaises(subprocess.TimeoutExpired) as ctx:
            subprocess.run(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                shell=False, capture_output=True, text=True, timeout=0.2)
        exc = ctx.exception
        err_raw = getattr(exc, "stderr", None)
        out_raw = getattr(exc, "stdout", None)
        if out_raw is None:
            out_raw = getattr(exc, "output", None)
        combined = (H._to_str(err_raw) + H._to_str(out_raw)).strip()
        self.assertIsInstance(combined, str)
        self.assertIsInstance(H.redact_text(combined or "timeout"), str)

    def test_timeout_bytes_decoded_no_typeerror(self):
        exc = subprocess.TimeoutExpired(cmd=["hcloud"], timeout=3,
                                        output=b"partial-\xff-out",
                                        stderr=b"partial-err")
        with patch.object(H.subprocess, "run", side_effect=exc):
            with self.assertRaises(H.HCloudError) as ctx:
                H.run(["server", "list"], _auth_token(), timeout=3)
        err = ctx.exception
        self.assertEqual(err.code, "TIMEOUT")
        self.assertIsInstance(str(err), str)
        self.assertTrue(err.stderr is None or isinstance(err.stderr, str))

    def test_proc_bytes_outputs_decoded(self):
        proc = subprocess.CompletedProcess(args=["hcloud"], returncode=1,
                                           stdout=b"\xff-binary", stderr=b"oops")
        with patch.object(H.subprocess, "run", return_value=proc):
            with self.assertRaises(H.HCloudError) as ctx:
                H.run(["server", "list"], _auth_token())
        self.assertEqual(ctx.exception.code, "HCLOUD_EXIT")
        self.assertIsInstance(ctx.exception.stderr, str)

    def test_not_found_structured(self):
        with patch.object(H.subprocess, "run", side_effect=FileNotFoundError()):
            with self.assertRaises(H.HCloudError) as ctx:
                H.run(["version"], _auth_none())
        self.assertEqual(ctx.exception.code, "HCLOUD_NOT_FOUND")

    def test_os_permission_structured(self):
        with patch.object(H.subprocess, "run", side_effect=PermissionError("denied")):
            with self.assertRaises(H.HCloudError) as ctx:
                H.run(["version"], _auth_none())
        self.assertEqual(ctx.exception.code, "HCLOUD_OS_ERROR")

    def test_decode_error_structured(self):
        with patch.object(H.subprocess, "run",
                          side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")):
            with self.assertRaises(H.HCloudError) as ctx:
                H.run(["version"], _auth_none())
        self.assertEqual(ctx.exception.code, "HCLOUD_DECODE_ERROR")


class AuthContextTest(unittest.TestCase):
    def test_token_xor_context(self):
        with patch.dict(os.environ, {"HCLOUD_TOKEN": "sekrit"}, clear=False):
            auth = H.resolve_auth(None)
            self.assertEqual(auth.source, "token")
            with self.assertRaises(H.HCloudError) as ctx:
                H.resolve_auth("proj")
            self.assertEqual(ctx.exception.code, "AUTH_AMBIGUOUS")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HCLOUD_TOKEN", None)
            auth = H.resolve_auth("proj")
            self.assertEqual(auth, H.Auth(context="proj", token_present=False, source="context"))
            missing = H.resolve_auth(None)
            self.assertEqual(missing.source, "none")
            with self.assertRaises(H.HCloudError) as ctx2:
                H.require_live_auth(missing)
            self.assertEqual(ctx2.exception.code, "AUTH_MISSING")

    def test_context_consistency_every_call(self):
        seen = []

        def fake_run(argv, **kwargs):
            seen.append(list(argv))
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="[]", stderr="")

        auth = _auth_ctx("pinned")
        with patch.object(H.subprocess, "run", side_effect=fake_run):
            H.run(["a"], auth)
            H.run(["b", "c"], auth)
        for argv in seen:
            self.assertEqual(argv[1:3], ["--context", "pinned"])

    def test_token_never_in_argv_refused(self):
        with patch.dict(os.environ, {"HCLOUD_TOKEN": "tok-abc-123"}, clear=False):
            auth = H.Auth(context=None, token_present=True, source="token")
            with self.assertRaises(H.HCloudError) as ctx:
                H.build_argv(["--token", "tok-abc-123"], auth)
            self.assertEqual(ctx.exception.code, "AUTH_LEAK_REFUSED")

    def test_child_env_strips_overrides_and_token_for_context(self):
        env = {"HCLOUD_TOKEN": "sekrit", "HCLOUD_ENDPOINT": "https://evil/x",
               "HCLOUD_HOST": "evil", "HCLOUD_DEBUG": "1", "KEEP": "1"}
        with patch.dict(os.environ, env, clear=True):
            child = H._child_env(_auth_ctx("p"))
            self.assertNotIn("HCLOUD_TOKEN", child)
            self.assertNotIn("HCLOUD_ENDPOINT", child)
            self.assertNotIn("HCLOUD_HOST", child)
            self.assertNotIn("HCLOUD_DEBUG", child)
            self.assertEqual(child.get("KEEP"), "1")
            child2 = H._child_env(_auth_token())
            self.assertEqual(child2.get("HCLOUD_TOKEN"), "sekrit")
            self.assertNotIn("HCLOUD_ENDPOINT", child2)


class RedactionTest(unittest.TestCase):
    def test_known_token_and_labeled_values_redacted(self):
        with patch.dict(os.environ, {"HCLOUD_TOKEN": "sekrit-xyz"}, clear=False):
            self.assertNotIn("sekrit-xyz", H.redact_text("auth sekrit-xyz done"))
            self.assertIn("[REDACTED]", H.redact_text("token=sekrit-xyz"))
            self.assertIn("[REDACTED]", H.redact_text("Authorization: Bearer abc"))
        self.assertIn("[REDACTED]", H.redact_text("api-key=abcdef"))

    def test_bearer_and_structured_assignments_redacted(self):
        secret = "synthetic-review-secret"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HCLOUD_TOKEN", None)
            out = H.redact_text("Authorization: Bearer " + secret)
            self.assertNotIn(secret, out)
            self.assertIn("Bearer [REDACTED]", out)
            out2 = H.redact_text("Bearer " + secret)
            self.assertNotIn(secret, out2)
            out3 = H.redact_text('{"token": "' + secret + '"}')
            self.assertNotIn(secret, out3)
            out4 = H.redact_text("{'token': '" + secret + "'}")
            self.assertNotIn(secret, out4)
            out5 = H.redact_obj({"token": secret, "nested": {"api_key": secret}})
            self.assertEqual(out5["token"], "[REDACTED]")
            self.assertEqual(out5["nested"]["api_key"], "[REDACTED]")

    def test_clamp_rejects_inf(self):
        self.assertEqual(H.clamp_timeout(float("inf")), 30)
        self.assertEqual(H.clamp_timeout(float("-inf")), 30)

    def test_sha256_digests_stay_printable(self):
        digest = "a" * 64
        plan_hash = f"sha256:{digest}"
        tag = {"plan_hash": plan_hash, "user_data_sha256": plan_hash}
        out = H.redact_obj(tag)
        self.assertEqual(out["plan_hash"], plan_hash)
        self.assertEqual(out["user_data_sha256"], plan_hash)
        self.assertEqual(H.redact_text(plan_hash), plan_hash)

    def test_error_snippet_truncated_and_redacted(self):
        with patch.dict(os.environ, {"HCLOUD_TOKEN": "sekrit-xyz"}, clear=False):
            proc = subprocess.CompletedProcess(
                args=["hcloud"], returncode=1, stdout="",
                stderr="token=sekrit-xyz " + "x" * 5000)
            with patch.object(H.subprocess, "run", return_value=proc):
                with self.assertRaises(H.HCloudError) as ctx:
                    H.run(["server", "list"], _auth_token())
        err = ctx.exception
        self.assertNotIn("sekrit-xyz", err.stderr or "")
        self.assertLessEqual(len(err.stderr or ""), 2200)


class VersionCompatTest(unittest.TestCase):
    def test_version_first_line_161_and_1701(self):
        from legends_hetzner import doctor as D
        for text in ("hcloud 1.61.0\n", "hcloud 1.70.1\n"):
            with patch.object(D, "run", return_value=text):
                with patch.object(D, "which_hcloud", return_value="/usr/bin/hcloud"):
                    report = D.offline(hcloud_bin="hcloud", timeout=5)
            self.assertTrue(report["hcloud_found"])
            self.assertIn(report["hcloud_version"], ("hcloud 1.61.0", "hcloud 1.70.1"))


if __name__ == "__main__":
    unittest.main()
