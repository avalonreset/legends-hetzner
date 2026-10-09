# SPDX-License-Identifier: MIT
"""Mocked tests: CLI contract, offline doctor, resources, version canary."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from legends_hetzner import __version__ as VERSION
from legends_hetzner import PROVISION_SUPPORT
from legends_hetzner import cli as CLI
from legends_hetzner import hcloud as H


class ContractTest(unittest.TestCase):
    def test_version_and_provision_canary(self):
        self.assertEqual(VERSION, "0.1.1")
        self.assertEqual(PROVISION_SUPPORT, "live-canary-validated: Windows client, Ubuntu 24.04 server; see docs/VALIDATION.md")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(CLI.main(["--version"]), 0)
        self.assertEqual(buf.getvalue().strip(), "0.1.1")

    def test_doctor_offline_no_auth(self):
        clean = {"mode": "offline", "version": "0.1.1",
                 "provision_support": PROVISION_SUPPORT,
                 "hcloud_found": True, "python_ok": True, "errors": []}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HCLOUD_TOKEN", None)
            with patch("legends_hetzner.doctor.offline", return_value=clean):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = CLI.main(["doctor"])
        self.assertEqual(code, 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["mode"], "offline")
        self.assertEqual(report["version"], "0.1.1")
        self.assertIn("live-canary-validated", report["provision_support"])

    def test_doctor_offline_missing_hcloud_nonzero(self):
        bad = {"mode": "offline", "version": "0.1.1", "hcloud_found": False,
               "python_ok": True,
               "errors": [{"code": "HCLOUD_NOT_FOUND", "message": "missing"}]}
        with patch("legends_hetzner.doctor.offline", return_value=bad):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = CLI.main(["doctor"])
        self.assertEqual(code, 1)

    def test_doctor_live_auth_missing_nonzero(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HCLOUD_TOKEN", None)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = CLI.main(["doctor", "--live"])
        self.assertEqual(code, 5)

    def test_doctor_live_invalid_shape_nonzero(self):
        with patch.dict(os.environ, {"HCLOUD_TOKEN": "t"}, clear=False):
            with patch("legends_hetzner.doctor.run_json", return_value=None):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = CLI.main(["doctor", "--live"])
        self.assertEqual(code, 1)

    def test_inventory_invalid_shape_rejected(self):
        with patch.dict(os.environ, {"HCLOUD_TOKEN": "t"}, clear=False):
            with patch("legends_hetzner.inventory.run_json", return_value={"weird": 1}):
                code = CLI.main(["inventory"])
        self.assertEqual(code, 1)

    def test_inventory_requires_auth(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HCLOUD_TOKEN", None)
            code = CLI.main(["inventory"])
        self.assertEqual(code, 5)

    def test_server_plan_and_preflight_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = str(Path(tmp) / "plan.json")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = CLI.main(["server", "plan", "--name", "web-1", "--type", "cx22",
                                 "--location", "fsn1", "--image", "ubuntu-24.04",
                                 "--ssh-key", "key-a", "--out", plan_file])
            self.assertEqual(code, 0)
            out = json.loads(buf.getvalue())
            self.assertTrue(out["plan_hash"].startswith("sha256:"))
            # Preflight without auth fails closed (no writes).
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("HCLOUD_TOKEN", None)
                self.assertEqual(CLI.main(["server", "preflight", "--plan", plan_file]), 5)

    def test_create_requires_approval_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = str(Path(tmp) / "plan.json")
            CLI.main(["server", "plan", "--name", "web-1", "--type", "cx22",
                      "--location", "fsn1", "--image", "img", "--ssh-key", "k",
                      "--out", plan_file])
            obj = json.loads(Path(plan_file).read_text(encoding="utf-8"))
            with patch.dict(os.environ, {"HCLOUD_TOKEN": "t"}, clear=False):
                # Missing --approve must fail validation with no write.
                code = CLI.main(["server", "create", "--plan", plan_file,
                                 "--plan-hash", obj["plan_hash"]])
            self.assertEqual(code, 2)

    def test_resources_absolute_paths(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(CLI.main(["resources"]), 0)
        data = json.loads(buf.getvalue())
        self.assertTrue(os.path.isabs(data["recipe"]))
        self.assertTrue(os.path.isabs(data["pack_dir"]))
        self.assertIn(data["source"], ("checkout", "package_data", "missing"))
        self.assertEqual(data["version"], "0.1.1")

    def test_context_flag_reaches_adapter(self):
        seen = {}
        real_resolve = CLI.resolve_auth

        def spy(context):
            seen["context"] = context
            return real_resolve(context)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HCLOUD_TOKEN", None)
            with patch.object(CLI, "resolve_auth", side_effect=spy):
                with patch("legends_hetzner.doctor.live",
                           return_value={"mode": "live", "live_ok": False, "errors": []}):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        code = CLI.main(["--context", "proj-a", "doctor", "--live"])
        self.assertEqual(seen.get("context"), "proj-a")
        self.assertEqual(code, 1)

    def test_resources_markers_and_wheel_data(self):
        from legends_hetzner import resources as R
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp) / "bare"
            (bare / "docs").mkdir(parents=True)
            (bare / "knowledge").mkdir(parents=True)
            self.assertFalse(R._has_markers(bare))
            (bare / "docs" / "CLI-CONTRACT.json").write_text("{}", encoding="utf-8")
            self.assertTrue(R._has_markers(bare))
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "pkg"
            data = pkg / "_data"
            (data / "docs").mkdir(parents=True)
            (data / "knowledge" / "hetzner").mkdir(parents=True)
            (data / "docs" / "AGENT-RECIPE.md").write_text("x", encoding="utf-8")
            (data / "knowledge" / "hetzner" / "pack.json").write_text("{}", encoding="utf-8")
            fake_init = pkg / "__init__.py"
            fake_init.write_text("", encoding="utf-8")
            with patch("legends_hetzner.resources.__file__", str(fake_init)):
                resolved = R.resolve()
            self.assertEqual(resolved["source"], "package_data")
            self.assertTrue(resolved["recipe_exists"])
            self.assertTrue(resolved["pack_exists"])


if __name__ == "__main__":
    unittest.main()
