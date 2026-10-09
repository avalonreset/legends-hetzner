# SPDX-License-Identifier: MIT
"""Tree-level release-gate tests (mechanism fixtures + live tree).

Fixture secrets are built with J() so committed sources carry no
flaggable literals; only the temp-dir fixtures contain them.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "check_release.py"
BS = chr(92)


def J(*parts: str) -> str:
    return "".join(parts)


def run_gate(root: Path, *extra: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(GATE), "--root", str(root),
         "--format", "json", *extra],
        capture_output=True, text=True, timeout=120)
    return proc.returncode, json.loads(proc.stdout)


def fail_codes(payload: dict) -> set[str]:
    return {f["code"] for f in payload["findings"] if f["level"] == "FAIL"}


def _png(name: str, width: int, height: int) -> bytes:
    return struct.pack(">8sI4sII5s", b"\x89PNG\r\n\x1a\n", 13, b"IHDR",
                       width, height, b"\x08\x02\x00\x00\x00")


def write_clean_tree(root: Path) -> None:
    (root / "legends_hetzner").mkdir(parents=True)
    (root / "legends_hetzner" / "__init__.py").write_text(
        '__version__ = "0.1.0"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0.1.0"\n'
        'requires-python=">=3.10"\nlicense="MIT"\n', encoding="utf-8")
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        (root / name).write_text("ok\n", encoding="utf-8")
    (root / ".gitignore").write_text(".env\n*.pem\n*.key\n",
                                     encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "AGENT-RECIPE.md").write_text("# r\n", encoding="utf-8")
    vault = root / "knowledge" / "hetzner" / "vault"
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# i\n", encoding="utf-8")
    digest = hashlib.sha256(b"# i\n").hexdigest()
    pack = {"schema": "legends.knowledge-pack/v1",
            "module": "legends-hetzner", "entrypoint": "index.md",
            "files": [{"path": "index.md", "sha256": digest}]}
    (root / "knowledge" / "hetzner" / "pack.json").write_text(
        json.dumps(pack), encoding="utf-8")
    flows = root / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "checks.yml").write_text("# fixture\n", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "banner.png").write_bytes(_png("b", 4096, 1024))
    (assets / "preview.png").write_bytes(_png("p", 1024, 256))
    (assets / "social-preview.png").write_bytes(_png("s", 1280, 640))


class TestGateMechanism(unittest.TestCase):
    def _fresh(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        write_clean_tree(root)
        return root

    def test_clean_tree_exit_zero(self):
        code, payload = run_gate(self._fresh())
        self.assertEqual(code, 0, payload["findings"])
        self.assertEqual(payload["fail"], 0)

    def test_missing_assets_fail(self):
        root = self._fresh()
        (root / "docs" / "AGENT-RECIPE.md").unlink()
        (root / "knowledge" / "hetzner" / "pack.json").unlink()
        (root / ".github" / "workflows" / "checks.yml").unlink()
        (root / "assets" / "banner.png").unlink()
        code, payload = run_gate(root)
        self.assertEqual(code, 1)
        codes = fail_codes(payload)
        for want in ("RECIPE_MISSING", "PACK_MANIFEST_MISSING",
                     "WORKFLOW_MISSING", "ASSET_MISSING"):
            self.assertIn(want, codes)

    def test_pack_hash_and_schema(self):
        root = self._fresh()
        (root / "knowledge" / "hetzner" / "vault" / "index.md").write_text(
            "# tampered\n", encoding="utf-8")
        code, payload = run_gate(root)
        self.assertEqual(code, 1)
        self.assertIn("PACK_HASH_MISMATCH", fail_codes(payload))
        root = self._fresh()
        manifest = root / "knowledge" / "hetzner" / "pack.json"
        manifest.write_text('{"schema": "other"}', encoding="utf-8")
        code, payload = run_gate(root)
        self.assertIn("PACK_SCHEMA", fail_codes(payload))

    def test_fingerprints_hit(self):
        root = self._fresh()
        (root / "docs" / "leak.md").write_text(
            J("path ", "E:", BS, "sample-kit") + "\n"
            + J("mail sample.user", "@gmail.com") + "\n"
            + J("ip ", "10.9.", "9.9") + "\n"
            + J("tok ", "HCLOUD_TOKEN", "=", "sample-secret-1") + "\n",
            encoding="utf-8")
        code, payload = run_gate(root)
        self.assertEqual(code, 1)
        codes = fail_codes(payload)
        for want in ("FP_DRIVE_PATH", "FP_EMAIL", "FP_PRIVATE_IP",
                     "FP_TOKEN_VALUE"):
            self.assertIn(want, codes)

    def test_documentation_ranges_and_placeholders_pass(self):
        root = self._fresh()
        (root / "docs" / "net.md").write_text(
            "example 203.0.113.7 and 169.254.169.254\n"
            + J("HCLOUD_TOKEN", "=", "<your", " token>") + "\n",
            encoding="utf-8")
        code, payload = run_gate(root)
        self.assertEqual(code, 0, payload["findings"])

    def test_public_identity_exempt(self):
        root = self._fresh()
        (root / "docs" / "pub.md").write_text(
            "https://github.com/avalonreset/legends-hetzner\n"
            "Copyright (c) Benjamin Samar\n", encoding="utf-8")
        code, payload = run_gate(root)
        self.assertEqual(code, 0, payload["findings"])

    def test_broken_link_and_bad_json(self):
        root = self._fresh()
        (root / "docs" / "a.md").write_text("[x](nope.md)\n",
                                            encoding="utf-8")
        (root / "docs" / "bad.json").write_text("{oops", encoding="utf-8")
        code, payload = run_gate(root)
        codes = fail_codes(payload)
        self.assertIn("LINK_BROKEN", codes)
        self.assertIn("JSON_INVALID", codes)

    def test_private_fingerprints_file(self):
        root = self._fresh()
        (root / "docs" / "n.md").write_text("SAMPLEHOUSE42\n",
                                            encoding="utf-8")
        pats = root / "pats.txt"
        pats.write_text("SAMPLEHOUSE\\d+ :: sample site pattern\n",
                        encoding="utf-8")
        code, payload = run_gate(root, "--fingerprints", str(pats))
        self.assertEqual(code, 1)
        self.assertIn("PRIV_SITE_MATCH", fail_codes(payload))
        code, _ = run_gate(root)
        self.assertEqual(code, 0)


class TestLiveTree(unittest.TestCase):
    def test_gate_green_on_release_tree(self):
        code, payload = run_gate(ROOT)
        self.assertEqual(code, 0, payload["findings"])
        self.assertEqual(payload["fail"], 0)
