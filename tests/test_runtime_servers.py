# SPDX-License-Identifier: MIT
"""Mocked tests: plans, current-schema preflight, dry-run, create honesty.

No live hcloud calls; runner_json/runner are fakes. Covers tamper/stale,
context binding, drift, location/arch/deprecation, receipt safety.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from legends_hetzner import hcloud as H
from legends_hetzner import servers as S


def _auth_token():
    return H.Auth(context=None, token_present=True, source="token")


def _auth_ctx(name="proj-a"):
    return H.Auth(context=name, token_present=False, source="context")


def _payload(**over):
    base = S.create_plan("web-1", "cx22", "fsn1", "ubuntu-24.04",
                         ["key-a"], planned_context=None)["plan"]
    base.update(over)
    return base


# Current-schema fixtures (post-Apr1 locations[], Nov2 deprecation objects).
def _type_ok():
    return {"id": 1, "name": "cx22", "architecture": "x86",
            "locations": [{"location": "fsn1", "available": True,
                           "recommended": True, "deprecation": None}]}


def _image_ok():
    return {"id": 10, "name": "ubuntu-24.04", "architecture": "x86",
            "deprecation": None}


def _fake_runner(mapping, calls=None):
    def run(argv, auth, timeout=None, hcloud_bin="hcloud"):
        if calls is not None:
            calls.append(list(argv))
        key = " ".join(argv[:2])
        if key == "server list":
            return list(mapping.get("servers", []))
        if key == "server-type list":
            return list(mapping.get("types", []))
        if key == "location list":
            return list(mapping.get("locations", []))
        if key == "image list":
            return list(mapping.get("images", []))
        if key == "ssh-key list":
            return list(mapping.get("keys", []))
        if key == "server describe":
            name = argv[2] if len(argv) > 2 else ""
            for item in mapping.get("servers", []):
                if item.get("name") == name or str(item.get("id", "")) == name:
                    return {"name": item.get("name"), "id": item.get("id")}
            raise H.HCloudError("HCLOUD_EXIT", "not found", exit_code=1)
        raise AssertionError(f"unexpected argv {argv}")
    return run


def _good_mapping():
    return {"servers": [], "types": [_type_ok()],
            "locations": [{"name": "fsn1"}],
            "images": [_image_ok()], "keys": [{"name": "key-a"}]}


class PlanFileTest(unittest.TestCase):
    def test_plan_requires_ssh_key(self):
        with self.assertRaises(S.PlanError):
            S.create_plan("n", "t", "l", "i", [])

    def test_plan_user_data_digest_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            ud = Path(tmp) / "ud.yaml"
            ud.write_text("#cloud-config\npackages: []\n", encoding="utf-8")
            obj = S.create_plan("web-1", "cx22", "fsn1", "ubuntu-24.04",
                                ["key-a"], user_data_path=str(ud))
            self.assertTrue(obj["plan"]["user_data_sha256"].startswith("sha256:"))
            plan_file = str(Path(tmp) / "plan.json")
            S.write_plan_file(obj, plan_file)
            payload, h = S.load_plan(plan_file, obj["plan_hash"], 24)
            self.assertEqual(h, obj["plan_hash"])
            # Tamper with user-data content: digest mismatch.
            tampered = json.loads(Path(plan_file).read_text(encoding="utf-8"))
            tampered["plan"]["user_data"] = "#cloud-config\npackages: [x]\n"
            Path(plan_file).write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(S.PlanError) as ctx:
                S.load_plan(plan_file, obj["plan_hash"], 24)
            self.assertIn(ctx.exception.code, ("PLAN_TAMPERED", "PLAN_HASH_MISMATCH"))

    def test_plan_hash_mismatch_and_stale(self):
        obj = S.create_plan("web-1", "cx22", "fsn1", "img", ["k"])
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = str(Path(tmp) / "p.json")
            S.write_plan_file(obj, plan_file)
            with self.assertRaises(S.PlanError) as ctx:
                S.load_plan(plan_file, "sha256:" + "0" * 64, 24)
            self.assertEqual(ctx.exception.code, "PLAN_HASH_MISMATCH")
            old = json.loads(Path(plan_file).read_text(encoding="utf-8"))
            old["plan"]["created_at"] = "2020-01-01T00:00:00Z"
            old["plan_hash"] = S.plan_hash_of(old["plan"])
            Path(plan_file).write_text(json.dumps(old), encoding="utf-8")
            with self.assertRaises(S.PlanError) as ctx2:
                S.load_plan(plan_file, old["plan_hash"], 24)
            self.assertEqual(ctx2.exception.code, "PLAN_STALE")

    def test_plan_refuses_overwrite(self):
        obj = S.create_plan("web-1", "cx22", "fsn1", "img", ["k"])
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = str(Path(tmp) / "p.json")
            S.write_plan_file(obj, plan_file)
            with self.assertRaises(S.PlanError) as ctx:
                S.write_plan_file(obj, plan_file)
            self.assertEqual(ctx.exception.code, "PLAN_EXISTS")


class ContextBindingTest(unittest.TestCase):
    def test_bind_and_enforce(self):
        obj = S.create_plan("web-1", "cx22", "fsn1", "img", ["k"], planned_context="proj-a")
        self.assertEqual(obj["plan"]["planned_context"], "proj-a")
        S.enforce_planned_context(obj["plan"], _auth_ctx("proj-a"))
        with self.assertRaises(S.PlanError) as ctx:
            S.enforce_planned_context(obj["plan"], _auth_ctx("other"))
        self.assertEqual(ctx.exception.code, "PLAN_CONTEXT_MISMATCH")
        token_plan = S.create_plan("w", "t", "l", "i", ["k"])["plan"]
        with self.assertRaises(S.PlanError):
            S.enforce_planned_context(token_plan, _auth_ctx("proj-a"))


class PreflightTest(unittest.TestCase):
    def test_pass_current_schema(self):
        payload = _payload()
        result = S.preflight(payload, _auth_token(), runner_json=_fake_runner(_good_mapping()))
        self.assertTrue(result["passed"], result)
        names = {c["check"] for c in result["checks"]}
        for want in ("location_supported", "location_available", "location_not_deprecated",
                     "image_not_deprecated", "arch_compatible"):
            self.assertIn(want, names)
        avail = next(c for c in result["checks"] if c["check"] == "location_available")
        self.assertIn("indication, not guarantee", avail["detail"])

    def test_failed_preflight_name_in_use(self):
        mapping = _good_mapping()
        mapping["servers"] = [{"name": "web-1"}]
        result = S.preflight(_payload(), _auth_token(), runner_json=_fake_runner(mapping))
        self.assertFalse(result["passed"])
        self.assertTrue(any(not c["ok"] and c["check"] == "name_available" for c in result["checks"]))

    def test_location_unsupported_and_arch_mismatch(self):
        mapping = _good_mapping()
        mapping["types"] = [{"id": 1, "name": "cx22", "architecture": "arm",
                             "locations": [{"location": "nbg1", "available": True,
                                            "deprecation": None}]}]
        result = S.preflight(_payload(), _auth_token(), runner_json=_fake_runner(mapping))
        self.assertFalse(result["passed"])
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertFalse(by_name["location_supported"]["ok"])
        self.assertFalse(by_name["arch_compatible"]["ok"])

    def test_deprecated_and_unavailable_rejected(self):
        mapping = _good_mapping()
        mapping["types"] = [{"id": 1, "name": "cx22", "architecture": "x86",
                             "locations": [{"location": "fsn1", "available": False,
                                            "deprecation": {"announced": "2026-01-01"}}]}]
        mapping["images"] = [{"id": 10, "name": "ubuntu-24.04", "architecture": "x86",
                              "deprecation": {"announced": "2026-01-01"}}]
        result = S.preflight(_payload(), _auth_token(), runner_json=_fake_runner(mapping))
        self.assertFalse(result["passed"])
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertFalse(by_name["location_available"]["ok"])
        self.assertFalse(by_name["location_not_deprecated"]["ok"])
        self.assertFalse(by_name["image_not_deprecated"]["ok"])

    def test_drift_missing_type_blocks(self):
        mapping = _good_mapping()
        mapping["types"] = []
        result = S.preflight(_payload(), _auth_token(), runner_json=_fake_runner(mapping))
        self.assertFalse(result["passed"])


class CreateHonestyTest(unittest.TestCase):
    def _write_plan(self, tmp, **over):
        obj = S.create_plan("web-1", "cx22", "fsn1", "ubuntu-24.04", ["key-a"])
        if over:
            obj["plan"].update(over)
            obj["plan_hash"] = S.plan_hash_of(obj["plan"])
        plan_file = str(Path(tmp) / "plan.json")
        S.write_plan_file(obj, plan_file)
        return plan_file, obj["plan_hash"]

    def test_dry_run_makes_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file, h = self._write_plan(tmp)
            write_calls: list = []

            def runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
                write_calls.append(list(argv))
                raise AssertionError("write attempted during dry-run")

            receipt = S.create_from_plan(plan_file, h, True, True, None, 24,
                                         _auth_token(), runner_json=_fake_runner(_good_mapping()),
                                         runner=runner)
            self.assertEqual(receipt["status"], "dry_run")
            self.assertEqual(write_calls, [])

    def test_needs_approval_and_single_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file, h = self._write_plan(tmp)
            with self.assertRaises(S.PlanError) as ctx:
                S.create_from_plan(plan_file, h, False, True, None, 24, _auth_token(),
                                   runner_json=_fake_runner(_good_mapping()))
            self.assertEqual(ctx.exception.code, "NEED_APPROVAL")
            calls: list = []

            def failing_runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
                calls.append(list(argv))
                raise H.HCloudError("HCLOUD_EXIT", "denied", exit_code=1, stderr="denied")

            with self.assertRaises(H.HCloudError):
                S.create_from_plan(plan_file, h, True, False, None, 24, _auth_token(),
                                   runner_json=_fake_runner(_good_mapping()),
                                   runner=failing_runner)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][:2], ["server", "create"])

    def test_receipt_path_validated_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file, h = self._write_plan(tmp)
            blocker = Path(tmp) / "receipt.json"
            blocker.write_text("existing", encoding="utf-8")
            writes: list = []

            def runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
                writes.append(argv)
                return "{}"

            with self.assertRaises(H.HCloudError) as ctx:
                S.create_from_plan(plan_file, h, True, False, str(blocker), 24,
                                   _auth_token(),
                                   runner_json=_fake_runner(_good_mapping()), runner=runner)
            self.assertEqual(ctx.exception.code, "RECEIPT_EXISTS")
            self.assertEqual(writes, [])

    def test_timeout_reports_uncertain_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file, h = self._write_plan(tmp)

            def timeout_runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
                raise H.HCloudError("TIMEOUT", "timed out after 30s: server.")

            # Readback itself fails -> uncertain_unknown (conservative, retained).
            with self.assertRaises(S.UncertainError) as ctx:
                S.create_from_plan(plan_file, h, True, False, None, 24, _auth_token(),
                                   runner_json=_fake_runner(_good_mapping()),
                                   runner=timeout_runner)
            self.assertEqual(ctx.exception.code, "UNCERTAIN_UNKNOWN")
            # Readback returns a different server -> uncertain_missing.
            mapping = _good_mapping()

            def mismatch_json(argv, auth, timeout=None, hcloud_bin="hcloud"):
                if argv[:2] == ["server", "describe"]:
                    return {"id": 5, "name": "other"}
                return _fake_runner(mapping)(argv, auth, timeout, hcloud_bin)

            with self.assertRaises(S.UncertainError) as ctx_mid:
                S.create_from_plan(plan_file, h, True, False, None, 24, _auth_token(),
                                   runner_json=mismatch_json, runner=timeout_runner)
            self.assertEqual(ctx_mid.exception.code, "UNCERTAIN_MISSING")
            # Present after timeout -> uncertain_exists (stateful: list empty
            # at preflight, describe finds the server after the write attempt).
            mapping2 = _good_mapping()

            def created_json(argv, auth, timeout=None, hcloud_bin="hcloud"):
                if argv[:2] == ["server", "describe"]:
                    return {"id": 99, "name": "web-1"}
                return _fake_runner(mapping2)(argv, auth, timeout, hcloud_bin)

            with self.assertRaises(S.UncertainError) as ctx2:
                S.create_from_plan(plan_file, h, True, False, None, 24, _auth_token(),
                                   runner_json=created_json, runner=timeout_runner)
            self.assertEqual(ctx2.exception.code, "UNCERTAIN_EXISTS")

    def test_failed_cli_with_existing_resource_is_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file, h = self._write_plan(tmp)
            mapping = _good_mapping()
            # Preflight sees free name, but readback finds it (created despite CLI error).
            state = {"describe_calls": 0}

            def runner_json(argv, auth, timeout=None, hcloud_bin="hcloud"):
                if argv[:2] == ["server", "describe"]:
                    state["describe_calls"] += 1
                    return {"name": "web-1", "id": 7}
                return _fake_runner(mapping)(argv, auth, timeout, hcloud_bin)

            def failing(argv, auth, timeout=None, hcloud_bin="hcloud"):
                raise H.HCloudError("HCLOUD_EXIT", "exit 1", exit_code=1)

            with self.assertRaises(S.UncertainError) as ctx:
                S.create_from_plan(plan_file, h, True, False, None, 24,
                                   _auth_token(), runner_json=runner_json, runner=failing)
            self.assertEqual(ctx.exception.code, "UNCERTAIN_EXISTS")

class LiveFixtureTest(unittest.TestCase):
    """Observed hcloud 1.61 shapes: name/id locations, duplicate images."""

    def test_old_cli_locations_name_id_pass_unknown_availability(self):
        payload = _payload()
        mapping = _good_mapping()
        mapping["types"] = [{"id": 22, "name": "cx22", "architecture": "x86",
                             "locations": [{"id": 1, "name": "fsn1", "deprecation": None},
                                           {"id": 2, "name": "nbg1", "deprecation": None}]}]
        result = S.preflight(payload, _auth_token(), runner_json=_fake_runner(mapping))
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertTrue(by_name["location_supported"]["ok"])
        self.assertTrue(by_name["location_available"]["ok"])
        self.assertIn("unknown", by_name["location_available"]["detail"].lower())
        self.assertNotIn("available=true", by_name["location_available"]["detail"])
        self.assertTrue(result["passed"], result)

    def test_image_duplicates_select_matching_arch(self):
        dupes = [{"id": 10, "name": "ubuntu-24.04", "architecture": "x86", "deprecation": None},
                 {"id": 11, "name": "ubuntu-24.04", "architecture": "arm", "deprecation": None}]
        # cax (arm) must not false-mismatch on first x86 record.
        arm_type = {"id": 31, "name": "cax11", "architecture": "arm",
                    "locations": [{"location": "fsn1", "available": True, "deprecation": None}]}
        mapping = _good_mapping()
        mapping["types"] = [arm_type]
        mapping["images"] = dupes
        payload = _payload(server_type="cax11")
        result = S.preflight(payload, _auth_token(), runner_json=_fake_runner(mapping))
        self.assertTrue(result["passed"], result)
        # x86 still passes.
        mapping["types"] = [_type_ok()]
        payload2 = _payload()
        result2 = S.preflight(payload2, _auth_token(), runner_json=_fake_runner(mapping))
        self.assertTrue(result2["passed"], result2)

    def test_exact_image_id_can_fail_incompatible(self):
        dupes = [{"id": 10, "name": "ubuntu-24.04", "architecture": "x86", "deprecation": None},
                 {"id": 11, "name": "ubuntu-24.04", "architecture": "arm", "deprecation": None}]
        arm_type = {"id": 31, "name": "cax11", "architecture": "arm",
                    "locations": [{"location": "fsn1", "available": True, "deprecation": None}]}
        mapping = _good_mapping()
        mapping["types"] = [arm_type]
        mapping["images"] = dupes
        payload = _payload(server_type="cax11", image="10")
        result = S.preflight(payload, _auth_token(), runner_json=_fake_runner(mapping))
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertFalse(by_name["arch_compatible"]["ok"])
        self.assertFalse(result["passed"])

    def test_readback_direct_by_numeric_id_confirms_created(self):
        # P1: describe {id:123,name} by "123" must confirm, not uncertain.
        with tempfile.TemporaryDirectory() as tmp:
            obj = S.create_plan("web-1", "cx22", "fsn1", "ubuntu-24.04", ["key-a"])
            plan_file = str(Path(tmp) / "plan.json")
            S.write_plan_file(obj, plan_file)
            mapping = _good_mapping()

            def runner_json(argv, auth, timeout=None, hcloud_bin="hcloud"):
                if argv[:2] == ["server", "describe"]:
                    return {"id": 123, "name": "web-1",
                            "server_type": {"name": "cx22"},
                            "location": {"name": "fsn1"},
                            "image": {"name": "ubuntu-24.04"}}
                return _fake_runner(mapping)(argv, auth, timeout, hcloud_bin)

            def runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
                self.assertEqual(argv[:2], ["server", "create"])
                return json.dumps({"server": {"id": 123, "name": "web-1"}})

            receipt = S.create_from_plan(plan_file, obj["plan_hash"], True, False,
                                         None, 24, _auth_token(),
                                         runner_json=runner_json, runner=runner)
            self.assertEqual(receipt["status"], "created")

    def test_readback_id_mismatch_is_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = S.create_plan("web-1", "cx22", "fsn1", "ubuntu-24.04", ["key-a"])
            plan_file = str(Path(tmp) / "plan.json")
            S.write_plan_file(obj, plan_file)
            mapping = _good_mapping()

            def runner_json(argv, auth, timeout=None, hcloud_bin="hcloud"):
                if argv[:2] == ["server", "describe"]:
                    return {"id": 999, "name": "web-1"}
                return _fake_runner(mapping)(argv, auth, timeout, hcloud_bin)

            def runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
                return json.dumps({"server": {"id": 123, "name": "web-1"}})

            with self.assertRaises(S.UncertainError) as ctx:
                S.create_from_plan(plan_file, obj["plan_hash"], True, False,
                                   None, 24, _auth_token(),
                                   runner_json=runner_json, runner=runner)
            self.assertEqual(ctx.exception.code, "UNCERTAIN_UNKNOWN")


class ReceiptRedactionTest(unittest.TestCase):
    def test_receipt_redacted_and_digests_printable(self):
        with tempfile.TemporaryDirectory() as tmp:
            ud = Path(tmp) / "ud.txt"
            ud.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
            obj = S.create_plan("web-1", "cx22", "fsn1", "ubuntu-24.04",
                                ["key-a"], user_data_path=str(ud))
            plan_file = str(Path(tmp) / "plan.json")
            S.write_plan_file(obj, plan_file)
            receipt_file = str(Path(tmp) / "receipt.json")
            with patch.dict(os.environ, {"HCLOUD_TOKEN": "sekrit-xyz"}, clear=False):
                receipt = S.create_from_plan(plan_file, obj["plan_hash"], True, True,
                                             receipt_file, 24, _auth_token(),
                                             runner_json=_fake_runner(_good_mapping()))
            body = Path(receipt_file).read_text(encoding="utf-8")
            self.assertNotIn("sekrit-xyz", body)
            self.assertNotIn("echo hi", body)
            self.assertEqual(receipt["plan_hash"], obj["plan_hash"])
            self.assertTrue(receipt["user_data_sha256"].startswith("sha256:"))
            self.assertIn(obj["plan_hash"], body)


class FreezeRegressionTest(unittest.TestCase):
    """Empty-hash bypass, naive time, non-finite age, incomplete provider data."""

    def _write(self, tmp, **over):
        obj = S.create_plan("web-1", "cx22", "fsn1", "ubuntu-24.04", ["key-a"])
        if over:
            obj["plan"].update(over)
            obj["plan_hash"] = S.plan_hash_of(obj["plan"])
        plan_file = str(Path(tmp) / "plan.json")
        S.write_plan_file(obj, plan_file)
        return plan_file, obj

    def test_empty_and_none_hash_never_reach_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file, obj = self._write(tmp)
            writes: list = []

            def runner(argv, auth, timeout=None, hcloud_bin="hcloud"):
                writes.append(argv)
                return "{}"

            for bad in ("", "   ", None, "not-a-hash", "sha256:xyz"):
                with self.subTest(bad=bad):
                    with self.assertRaises(S.PlanError) as ctx:
                        S.create_from_plan(plan_file, bad, True, False, None, 24,
                                           _auth_token(),
                                           runner_json=_fake_runner(_good_mapping()),
                                           runner=runner)
                    self.assertEqual(ctx.exception.code, "PLAN_HASH_MISMATCH")
            self.assertEqual(writes, [])
            # None stays legal for offline load (preflight path).
            payload, h = S.load_plan(plan_file, None, 24)
            self.assertEqual(h, obj["plan_hash"])

    def test_naive_created_at_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file, obj = self._write(tmp)
            tampered = json.loads(Path(plan_file).read_text(encoding="utf-8"))
            tampered["plan"]["created_at"] = "2026-01-01T00:00:00"
            tampered["plan_hash"] = S.plan_hash_of(tampered["plan"])
            Path(plan_file).write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(S.PlanError) as ctx:
                S.load_plan(plan_file, tampered["plan_hash"], 24)
            self.assertEqual(ctx.exception.code, "PLAN_INVALID")

    def test_nonfinite_max_age_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file, obj = self._write(tmp)
            for bad in (float("nan"), float("inf"), 0, -5, "soon"):
                with self.subTest(bad=bad):
                    with self.assertRaises(S.PlanError) as ctx:
                        S.load_plan(plan_file, obj["plan_hash"], bad)
                    self.assertEqual(ctx.exception.code, "PLAN_INVALID")

    def test_missing_locations_blocks(self):
        payload = _payload()
        mapping = _good_mapping()
        mapping["types"] = [{"id": 1, "name": "cx22", "architecture": "x86"}]
        result = S.preflight(payload, _auth_token(), runner_json=_fake_runner(mapping))
        self.assertFalse(result["passed"])
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertFalse(by_name["location_supported"]["ok"])

    def test_missing_arch_blocks(self):
        payload = _payload()
        mapping = _good_mapping()
        mapping["types"] = [{"id": 1, "name": "cx22",
                             "locations": [{"location": "fsn1", "available": True,
                                            "deprecation": None}]}]
        result = S.preflight(payload, _auth_token(), runner_json=_fake_runner(mapping))
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertFalse(by_name["arch_compatible"]["ok"])
        self.assertFalse(result["passed"])

    def test_ssh_key_numeric_id_accepted(self):
        payload = _payload(ssh_keys=["4242"])
        mapping = _good_mapping()
        mapping["keys"] = [{"id": 4242, "name": "laptop"}]
        result = S.preflight(payload, _auth_token(), runner_json=_fake_runner(mapping))
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertTrue(by_name["ssh_keys_exist"]["ok"], result)

    def test_location_numeric_id_accepted(self):
        payload = _payload(location="1")
        mapping = _good_mapping()
        mapping["locations"] = [{"id": 1, "name": "fsn1"}]
        mapping["types"] = [{"id": 22, "name": "cx22", "architecture": "x86",
                             "locations": [{"id": 1, "name": "fsn1", "deprecation": None}]}]
        result = S.preflight(payload, _auth_token(), runner_json=_fake_runner(mapping))
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertTrue(by_name["location_exists"]["ok"], result)
        self.assertTrue(by_name["location_supported"]["ok"], result)

    def test_malformed_probe_shape_rejected(self):
        payload = _payload()

        def bad_json(argv, auth, timeout=None, hcloud_bin="hcloud"):
            if argv[:2] == ["server", "list"]:
                return {"unexpected": "dict"}
            return _fake_runner(_good_mapping())(argv, auth, timeout, hcloud_bin)

        with self.assertRaises(H.HCloudError) as ctx:
            S.preflight(payload, _auth_token(), runner_json=bad_json)
        self.assertEqual(ctx.exception.code, "HCLOUD_BAD_JSON")


if __name__ == "__main__":
    unittest.main()
