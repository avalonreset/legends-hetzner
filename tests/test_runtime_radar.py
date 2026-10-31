# SPDX-License-Identifier: MIT
"""Unit tests for legends-hetzner v0.1.3 radar, server snipe, and REST enrichment."""

from __future__ import annotations

import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from legends_hetzner import cli, hcloud, radar, servers


def _sample_server_types(
    *,
    cx43_fsn1: bool | None = False,
    cx33_fsn1: bool | None = False,
    cx23_hel1: bool | None = False,
    cax11_hel1: bool | None = False,
    include_category: bool = True,
) -> list[dict]:
    def _locs(fsn1_avail, nbg1_avail, hel1_avail):
        out = []
        for idx, (name, av) in enumerate(
            (("fsn1", fsn1_avail), ("nbg1", nbg1_avail), ("hel1", hel1_avail)), start=1
        ):
            entry = {"id": idx, "name": name, "deprecation": None}
            if av is not None:
                entry["available"] = av
                entry["recommended"] = av
            out.append(entry)
        return out

    def _prices(monthly: str, hourly: str) -> list[dict]:
        return [
            {
                "location": loc,
                "price_monthly": {"net": monthly, "gross": monthly},
                "price_hourly": {"net": hourly, "gross": hourly},
            }
            for loc in ("fsn1", "nbg1", "hel1")
        ]

    items = [
        {
            "id": 101,
            "name": "cx23",
            "architecture": "x86",
            "cores": 2,
            "memory": 4,
            "disk": 40,
            "locations": _locs(False, False, cx23_hel1),
            "prices": _prices("3.4900", "0.0056"),
        },
        {
            "id": 102,
            "name": "cx33",
            "architecture": "x86",
            "cores": 4,
            "memory": 8,
            "disk": 80,
            "locations": _locs(cx33_fsn1, False, False),
            "prices": _prices("5.4900", "0.0088"),
        },
        {
            "id": 103,
            "name": "cx43",
            "architecture": "x86",
            "cores": 8,
            "memory": 16,
            "disk": 160,
            "locations": _locs(cx43_fsn1, False, False),
            "prices": _prices("9.4900", "0.0152"),
        },
        {
            "id": 104,
            "name": "cax11",
            "architecture": "arm",
            "cores": 2,
            "memory": 4,
            "disk": 40,
            "locations": _locs(False, False, cax11_hel1),
            "prices": _prices("3.7900", "0.0060"),
        },
        {
            "id": 201,
            "name": "cpx22",
            "architecture": "x86",
            "cores": 2,
            "memory": 4,
            "disk": 80,
            "locations": _locs(True, True, True),
            "prices": _prices("7.9900", "0.0128"),
        },
    ]
    if include_category:
        for item in items:
            item["category"] = (
                "regular_purpose" if item["name"].startswith("cpx") else "cost_optimized"
            )
    return items


class TestRadarAndSniper(unittest.TestCase):
    def setUp(self):
        self.auth = hcloud.Auth(context=None, token_present=True, source="token")

    def test_radar_orders_by_cto_priority_and_filters_cost_optimized(self):
        st_list = _sample_server_types(
            cx43_fsn1=False, cx33_fsn1=True, cx23_hel1=True, cax11_hel1=True
        )
        report = radar.run_radar(
            self.auth,
            runner_json=lambda args, *a, **kw: st_list,
        )
        self.assertTrue(report["any_available"])
        self.assertEqual(report["available_count"], 3)
        # Matrix order follows CTO priority: cx43 -> cx33 -> cx23 -> cax11 (cpx22 excluded by default)
        self.assertEqual(
            [m["name"] for m in report["matrix"]],
            ["cx43", "cx33", "cx23", "cax11"],
        )
        # Recommended match should be cx33 in fsn1 (rank 2 beats cx23 rank 3 and cax11 rank 7)
        self.assertEqual(report["recommended_match"]["server_type"], "cx33")
        self.assertEqual(report["recommended_match"]["location"], "fsn1")
        self.assertEqual(report["recommended_match"]["price_monthly_net"], "5.4900")
        self.assertIn("x86_ladder", report["cto_doctrine"])

    def test_radar_germany_only_and_arch_filters(self):
        st_list = _sample_server_types(
            cx43_fsn1=False, cx33_fsn1=False, cx23_hel1=True, cax11_hel1=True
        )
        report = radar.run_radar(
            self.auth,
            germany_only=True,
            arch="x86",
            runner_json=lambda args, *a, **kw: st_list,
        )
        self.assertEqual(report["filters"]["locations"], ["fsn1", "nbg1"])
        self.assertEqual(report["filters"]["architecture"], "x86")
        self.assertFalse(report["any_available"])
        self.assertIsNone(report["recommended_match"])
        self.assertTrue(all(m["architecture"] == "x86" for m in report["matrix"]))

    def test_radar_unknown_availability_never_counts_as_available(self):
        st_list = _sample_server_types(
            cx43_fsn1=None, cx33_fsn1=None, cx23_hel1=None, cax11_hel1=None
        )
        report = radar.run_radar(
            self.auth,
            runner_json=lambda args, *a, **kw: st_list,
        )
        self.assertFalse(report["any_available"])
        self.assertEqual(report["available_count"], 0)
        self.assertEqual(
            report["matrix"][0]["locations"]["fsn1"]["available"], "unknown"
        )

    def test_radar_enforces_rate_limit_floor_and_watch_bounds(self):
        with self.assertRaises(servers.PlanError) as ctx:
            radar.run_radar(
                self.auth,
                watch=True,
                interval=2,
                runner_json=lambda *a, **kw: [],
            )
        self.assertEqual(ctx.exception.code, "RADAR_INTERVAL_TOO_LOW")

        with self.assertRaises(servers.PlanError) as ctx2:
            radar.run_radar(
                self.auth,
                watch=False,
                max_polls=5,
                runner_json=lambda *a, **kw: [],
            )
        self.assertEqual(ctx2.exception.code, "RADAR_WATCH_REQUIRED")

        with self.assertRaises(servers.PlanError) as ctx3:
            radar.run_radar(
                self.auth,
                germany_only=True,
                locations="fsn1,hel1",
                runner_json=lambda *a, **kw: [],
            )
        self.assertEqual(ctx3.exception.code, "RADAR_INVALID_FILTER")

    def test_radar_watch_polls_until_seat_opens(self):
        polls = [
            _sample_server_types(cx43_fsn1=False),
            _sample_server_types(cx43_fsn1=False),
            _sample_server_types(cx43_fsn1=True),
        ]
        idx = {"n": 0}
        sleeps: list[float] = []

        def fake_runner(args, *a, **kw):
            cur = polls[min(idx["n"], len(polls) - 1)]
            idx["n"] += 1
            return cur

        report = radar.run_radar(
            self.auth,
            types="cx43",
            germany_only=True,
            watch=True,
            interval=45,
            jitter=5,
            max_polls=10,
            runner_json=fake_runner,
            sleep_fn=lambda d: sleeps.append(d),
            rand_fn=lambda a, b: 3.0,
        )
        self.assertTrue(report["any_available"])
        self.assertEqual(report["watch"]["polls_completed"], 3)
        self.assertEqual(sleeps, [48.0, 48.0])
        self.assertEqual(report["recommended_match"]["server_type"], "cx43")

    def test_snipe_aborts_on_poll_1_when_non_capacity_check_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            receipt_path = Path(tmp) / "receipt.json"
            plan_obj = servers.create_plan(
                "dup-name", "cx43", "fsn1", "ubuntu-24.04", ["my-key"]
            )
            servers.write_plan_file(plan_obj, str(plan_path))

            calls = {"server_list": 0}
            sleeps: list[float] = []

            def fake_runner_json(args, *a, **kw):
                if args[:2] == ["server", "list"]:
                    calls["server_list"] += 1
                    # Duplicate server name already exists -> permanent preflight failure
                    return [{"id": 1, "name": "dup-name"}]
                if args[:2] == ["server-type", "list"]:
                    return _sample_server_types(cx43_fsn1=False)
                if args[:2] == ["location", "list"]:
                    return [{"id": 1, "name": "fsn1"}]
                if args[:2] == ["image", "list"]:
                    return [
                        {
                            "id": 10,
                            "name": "ubuntu-24.04",
                            "architecture": "x86",
                            "deprecation": None,
                        }
                    ]
                if args[:2] == ["ssh-key", "list"]:
                    return [{"id": 20, "name": "my-key"}]
                return []

            with self.assertRaises(servers.PreflightBlocked):
                radar.snipe_from_plan(
                    str(plan_path),
                    plan_obj["plan_hash"],
                    True,
                    False,
                    str(receipt_path),
                    24,
                    self.auth,
                    interval=30,
                    jitter=0,
                    max_polls=5,
                    runner_json=fake_runner_json,
                    sleep_fn=lambda d: sleeps.append(d),
                )
            self.assertEqual(calls["server_list"], 1)
            self.assertEqual(sleeps, [])
            saved = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "blocked")
            self.assertEqual(saved["snipe"]["polls_completed"], 1)
            self.assertEqual(saved["snipe"]["reason"], "permanent_preflight_failure")

    def test_snipe_polls_capacity_then_creates_once_when_seat_opens(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            receipt_path = Path(tmp) / "receipt.json"
            plan_obj = servers.create_plan(
                "snipe-target", "cx43", "fsn1", "ubuntu-24.04", ["my-key"]
            )
            servers.write_plan_file(plan_obj, str(plan_path))

            poll_state = {"st_calls": 0, "creates": 0}
            sleeps: list[float] = []

            def fake_runner_json(args, *a, **kw):
                if args[:2] == ["server", "list"]:
                    return []
                if args[:2] == ["server-type", "list"]:
                    poll_state["st_calls"] += 1
                    # Available on poll 2!
                    is_open = poll_state["st_calls"] >= 2
                    return _sample_server_types(cx43_fsn1=is_open)
                if args[:2] == ["location", "list"]:
                    return [{"id": 1, "name": "fsn1"}]
                if args[:2] == ["image", "list"]:
                    return [
                        {
                            "id": 10,
                            "name": "ubuntu-24.04",
                            "architecture": "x86",
                            "deprecation": None,
                        }
                    ]
                if args[:2] == ["ssh-key", "list"]:
                    return [{"id": 20, "name": "my-key"}]
                if args[:2] == ["server", "describe"]:
                    return {
                        "id": 999,
                        "name": "snipe-target",
                        "server_type": {"name": "cx43"},
                        "location": {"name": "fsn1"},
                        "image": {"name": "ubuntu-24.04"},
                    }
                return []

            def fake_runner(args, *a, **kw):
                if args[:2] == ["server", "create"]:
                    poll_state["creates"] += 1
                    return json.dumps(
                        {
                            "server": {
                                "id": 999,
                                "name": "snipe-target",
                                "status": "initializing",
                            }
                        }
                    )
                return "{}"

            receipt = radar.snipe_from_plan(
                str(plan_path),
                plan_obj["plan_hash"],
                True,
                False,
                str(receipt_path),
                24,
                self.auth,
                interval=30,
                jitter=5,
                max_polls=5,
                runner_json=fake_runner_json,
                runner=fake_runner,
                sleep_fn=lambda d: sleeps.append(d),
                rand_fn=lambda a, b: 2.0,
            )
            self.assertEqual(poll_state["creates"], 1)
            self.assertEqual(sleeps, [32.0])
            self.assertEqual(receipt["status"], "created")
            self.assertEqual(receipt["snipe"]["polls_completed"], 2)
            self.assertEqual(receipt["snipe"]["reason"], "capacity_open")

    def test_allow_unavailable_attempts_direct_api_placement_when_catalog_sold_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            receipt_path = Path(tmp) / "receipt.json"
            plan_obj = servers.create_plan(
                "direct-api-cx43", "cx43", "fsn1", "ubuntu-24.04", ["my-key"]
            )
            servers.write_plan_file(plan_obj, str(plan_path))

            creates = {"n": 0}

            def fake_runner_json(args, *a, **kw):
                if args[:2] == ["server", "list"]:
                    return []
                if args[:2] == ["server-type", "list"]:
                    # Catalog reports available=false ("Sold out" in Web Console)
                    return _sample_server_types(cx43_fsn1=False)
                if args[:2] == ["location", "list"]:
                    return [{"id": 1, "name": "fsn1"}]
                if args[:2] == ["image", "list"]:
                    return [
                        {
                            "id": 10,
                            "name": "ubuntu-24.04",
                            "architecture": "x86",
                            "deprecation": None,
                        }
                    ]
                if args[:2] == ["ssh-key", "list"]:
                    return [{"id": 20, "name": "my-key"}]
                if args[:2] == ["server", "describe"]:
                    return {
                        "id": 777,
                        "name": "direct-api-cx43",
                        "server_type": {"name": "cx43"},
                        "location": {"name": "fsn1"},
                        "image": {"name": "ubuntu-24.04"},
                    }
                return []

            def fake_runner(args, *a, **kw):
                if args[:2] == ["server", "create"]:
                    creates["n"] += 1
                    return json.dumps(
                        {
                            "server": {
                                "id": 777,
                                "name": "direct-api-cx43",
                                "status": "initializing",
                            }
                        }
                    )
                return "{}"

            receipt = servers.create_from_plan(
                str(plan_path),
                plan_obj["plan_hash"],
                True,
                False,
                str(receipt_path),
                24,
                self.auth,
                runner_json=fake_runner_json,
                runner=fake_runner,
                allow_unavailable=True,
            )
            self.assertEqual(creates["n"], 1)
            self.assertEqual(receipt["status"], "created")
            loc_check = next(
                c for c in receipt["preflight"]["checks"] if c["check"] == "location_available"
            )
            self.assertTrue(loc_check["ok"])
            self.assertIn("--allow-unavailable", loc_check["detail"])

    def test_rest_enrichment_for_hcloud_161_server_types(self):
        # Simulate hcloud 1.61 output: no category and no available boolean in locations[]
        cli_items = _sample_server_types(
            cx43_fsn1=None,
            cx33_fsn1=None,
            cx23_hel1=None,
            cax11_hel1=None,
            include_category=False,
        )
        rest_payload = {
            "server_types": _sample_server_types(
                cx43_fsn1=False,
                cx33_fsn1=True,
                cx23_hel1=False,
                cax11_hel1=True,
                include_category=True,
            ),
            "meta": {"pagination": {"page": 1, "next_page": None}},
        }

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n=-1):
                return json.dumps(rest_payload).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "cli.toml"
            toml_path.write_text(
                'active_context = "prod"\n[[contexts]]\nname = "prod"\ntoken = "ctx-secret-token-98765"\n',
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"HCLOUD_CONFIG": str(toml_path)}, clear=False):
                ctx_auth = hcloud.Auth(
                    context="prod", token_present=False, source="context"
                )
                enriched, did_enrich = hcloud.enrich_server_types_via_rest(
                    cli_items,
                    ctx_auth,
                    timeout=10,
                    opener=lambda req, timeout=10: FakeResp(),
                )
                self.assertTrue(did_enrich)
                cx33 = next(i for i in enriched if i["name"] == "cx33")
                self.assertEqual(cx33["category"], "cost_optimized")
                fsn1_loc = next(l for l in cx33["locations"] if l["name"] == "fsn1")
                self.assertIs(fsn1_loc["available"], True)
                # Ensure context token resolved from cli.toml is redacted by redact_text
                self.assertNotIn(
                    "ctx-secret-token-98765",
                    hcloud.redact_text("leaked ctx-secret-token-98765 here"),
                )

    def test_cli_radar_and_snipe_entrypoints(self):
        st_list = _sample_server_types(
            cx43_fsn1=False, cx33_fsn1=False, cx23_hel1=False, cax11_hel1=False
        )
        with mock.patch.dict(
            os.environ, {"HCLOUD_TOKEN": "test-secret-token-12345"}, clear=False
        ):
            with mock.patch(
                "legends_hetzner.radar.run_json", return_value=st_list
            ), mock.patch("legends_hetzner.radar.time.sleep"):
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc = cli.main(["radar", "--germany-only"])
                self.assertEqual(rc, 0)
                parsed = json.loads(buf.getvalue())
                self.assertFalse(parsed["any_available"])

                # Watch mode when nothing is available returns EXIT_PREFLIGHT (3)
                buf2 = io.StringIO()
                with mock.patch("sys.stdout", buf2):
                    rc2 = cli.main(
                        [
                            "radar",
                            "--germany-only",
                            "--watch",
                            "--interval",
                            "30",
                            "--jitter",
                            "0",
                            "--max-polls",
                            "2",
                        ]
                    )
                self.assertEqual(rc2, 3)

    def test_radar_cto_strategy_and_unmatched_types(self):
        st_list = _sample_server_types(
            cx43_fsn1=False, cx33_fsn1=False, cx23_hel1=False, cax11_hel1=False
        )
        report = radar.run_radar(
            self.auth,
            types="cx43,cx33,nonexistent-tier",
            germany_only=True,
            runner_json=lambda args, *a, **kw: st_list,
        )
        self.assertFalse(report["any_available"])
        self.assertEqual(report["filters"]["unmatched_types"], ["nonexistent-tier"])
        self.assertIn("cto_strategy", report)
        top_target = report["cto_strategy"]["top_direct_api_target"]
        self.assertIsNotNone(top_target)
        self.assertEqual(top_target["server_type"], "cx43")
        self.assertEqual(top_target["location"], "fsn1")
        self.assertEqual(top_target["catalog_available"], False)
        self.assertTrue(len(report["cto_strategy"]["direct_api_candidates"]) >= 2)

    def test_watch_params_reject_booleans_and_floats(self):
        defaults = {"watch": True, "interval": 45, "jitter": 5, "max_polls": 10}
        for bad_kwargs, expected_code in (
            ({"interval": True}, "RADAR_INVALID_INTERVAL"),
            ({"jitter": False}, "RADAR_INVALID_JITTER"),
            ({"max_polls": True}, "RADAR_POLLS_OUT_OF_RANGE"),
            ({"interval": 45.5}, "RADAR_INVALID_INTERVAL"),
        ):
            merged = {**defaults, **bad_kwargs}
            with self.subTest(bad_kwargs=bad_kwargs):
                with self.assertRaises(servers.PlanError) as ctx:
                    radar.validate_watch_params(**merged)
                self.assertEqual(ctx.exception.code, expected_code)

    def test_rest_enrichment_handles_http_client_disconnect_gracefully(self):
        cli_items = _sample_server_types(
            cx43_fsn1=None,
            cx33_fsn1=None,
            cx23_hel1=None,
            cax11_hel1=None,
            include_category=False,
        )

        def broken_opener(req, timeout=10):
            raise http.client.RemoteDisconnected("Remote end closed connection")

        with mock.patch.dict(
            os.environ, {"HCLOUD_TOKEN": "test-secret-token-12345"}, clear=False
        ):
            enriched, did_enrich = hcloud.enrich_server_types_via_rest(
                cli_items,
                self.auth,
                timeout=5,
                opener=broken_opener,
            )
            self.assertFalse(did_enrich)
            self.assertEqual(enriched, cli_items)

    def test_cli_allow_unavailable_and_create_error_exit_codes(self):
        st_list = _sample_server_types(cx43_fsn1=False)
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            receipt_path = Path(tmp) / "receipt.json"
            plan_obj = servers.create_plan(
                "edge-case-srv", "cx43", "fsn1", "ubuntu-24.04", ["my-key"]
            )
            servers.write_plan_file(plan_obj, str(plan_path))

            def fake_runner_json(args, *a, **kw):
                if args[:2] == ["server", "list"]:
                    return []
                if args[:2] == ["server-type", "list"]:
                    return st_list
                if args[:2] == ["location", "list"]:
                    return [{"id": 1, "name": "fsn1"}]
                if args[:2] == ["image", "list"]:
                    return [
                        {
                            "id": 10,
                            "name": "ubuntu-24.04",
                            "architecture": "x86",
                            "deprecation": None,
                        }
                    ]
                if args[:2] == ["ssh-key", "list"]:
                    return [{"id": 20, "name": "my-key"}]
                return []

            def failing_create_runner(args, *a, **kw):
                if args[:2] == ["server", "create"]:
                    raise hcloud.HCloudError(
                        "HCLOUD_EXIT",
                        "resource_unavailable: placement full",
                        exit_code=1,
                    )
                return "{}"

            with mock.patch.dict(
                os.environ, {"HCLOUD_TOKEN": "test-secret-token-12345"}, clear=False
            ):
                with mock.patch(
                    "legends_hetzner.servers.run_json", side_effect=fake_runner_json
                ), mock.patch(
                    "legends_hetzner.servers.run", side_effect=failing_create_runner
                ):
                    # 1. preflight without --allow-unavailable returns EXIT_PREFLIGHT (3)
                    buf1 = io.StringIO()
                    with mock.patch("sys.stdout", buf1):
                        rc1 = cli.main(["server", "preflight", "--plan", str(plan_path)])
                    self.assertEqual(rc1, cli.EXIT_PREFLIGHT)

                    # 2. preflight WITH --allow-unavailable returns 0
                    buf2 = io.StringIO()
                    with mock.patch("sys.stdout", buf2):
                        rc2 = cli.main(
                            [
                                "server",
                                "preflight",
                                "--plan",
                                str(plan_path),
                                "--allow-unavailable",
                            ]
                        )
                    self.assertEqual(rc2, 0)

                    # 3. server create WITH --allow-unavailable when hcloud create fails returns EXIT_CREATE (4)
                    buf3 = io.StringIO()
                    err3 = io.StringIO()
                    with mock.patch("sys.stdout", buf3), mock.patch("sys.stderr", err3):
                        rc3 = cli.main(
                            [
                                "server",
                                "create",
                                "--plan",
                                str(plan_path),
                                "--plan-hash",
                                plan_obj["plan_hash"],
                                "--approve",
                                "--allow-unavailable",
                                "--receipt",
                                str(receipt_path),
                            ]
                        )
                    self.assertEqual(rc3, cli.EXIT_CREATE)

    def test_radar_types_ascending_order_preserves_cto_priority(self):
        st_list = _sample_server_types(
            cx43_fsn1=False, cx33_fsn1=True, cx23_hel1=True
        )
        report = radar.run_radar(
            self.auth,
            types="cx23,cx33,cx43",
            runner_json=lambda args, *a, **kw: st_list,
        )
        self.assertEqual(
            [m["name"] for m in report["matrix"]],
            ["cx43", "cx33", "cx23"],
        )
        self.assertEqual(report["recommended_match"]["server_type"], "cx33")
        self.assertEqual(
            report["cto_strategy"]["top_direct_api_target"]["server_type"], "cx43"
        )

    def test_radar_offline_flag_validation_before_auth(self):
        env_clean = {k: v for k, v in os.environ.items() if k != "HCLOUD_TOKEN"}
        with mock.patch.dict(os.environ, env_clean, clear=True):
            err = io.StringIO()
            with mock.patch("sys.stderr", err):
                rc1 = cli.main(["radar", "--interval", "2", "--watch"])
                rc2 = cli.main(["radar", "--germany-only", "--locations", "hel1"])
            self.assertEqual(rc1, cli.EXIT_USAGE)
            self.assertEqual(rc2, cli.EXIT_USAGE)

    def test_hcloud_config_candidates_handles_missing_home(self):
        env_clean = {
            k: v
            for k, v in os.environ.items()
            if k not in ("HCLOUD_CONFIG", "APPDATA", "XDG_CONFIG_HOME")
        }
        with mock.patch.dict(os.environ, env_clean, clear=True):
            with mock.patch(
                "legends_hetzner.hcloud.Path.home",
                side_effect=RuntimeError("Could not determine home directory"),
            ):
                candidates = hcloud._hcloud_config_candidates()
                self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
