"""Exercise this pack against an installed Empire source in a temporary vault.

This is optional integration acceptance, not part of installation. It never
selects or changes a user's vault. Run on POSIX with persistent file permissions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--empire-source", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    args = parser.parse_args()
    if os.name == "nt":
        parser.error("Empire attachment apply requires POSIX; use WSL, Linux or macOS.")
    sys.path.insert(0, str(args.empire_source.resolve()))
    from claude_empire.knowledge import attachment_bundle, load_pack
    from claude_empire.transaction import TransactionError, apply_bundle, inspect_bundle

    with tempfile.TemporaryDirectory(prefix="legends-hetzner-pack-") as temporary:
        root = Path(temporary).resolve()
        vault = root / "synthetic-vault"
        (vault / "wiki").mkdir(parents=True)
        (vault / ".raw").mkdir()
        source = root / "module"
        shutil.copytree(args.pack.resolve().parent, source)
        pack = source / "pack.json"
        original = json.loads(pack.read_text(encoding="utf-8"))
        load_pack(pack)
        shelf = vault / original["ontology"]["suggested_home"]
        checks = []

        def bundle(identity):
            return attachment_bundle(
                vault, pack, operation_id=identity,
                generated_at="2026-10-09T12:00:00Z")

        def apply(candidate):
            approval = inspect_bundle(vault, candidate)["approval_sha256"]
            return apply_bundle(vault, candidate, approved_plan_sha256=approval)

        first = bundle("first-attach")
        inspect_bundle(vault, first)
        assert not shelf.exists(), "Preview changed the vault."
        checks.append("preview has no writes")
        apply(first)
        assert (shelf / "reference" / original["entrypoint"]).is_file()
        checks.append("fresh attachment")
        assert bundle("repeat-attach")["writes"] == []
        checks.append("repeat attachment is noop")
        index = shelf / "index.md"
        index.write_text("# User-owned index\n", encoding="utf-8")
        private = vault / "wiki" / "private-decisions.md"
        private.write_text("# Private choices\n", encoding="utf-8")
        changed = source / "vault" / original["entrypoint"]
        changed.write_text(changed.read_text(encoding="utf-8") + "\nSynthetic update.\n",
                           encoding="utf-8")
        updated = json.loads(pack.read_text(encoding="utf-8"))
        updated["version"] = "0.1.1"
        for item in updated["files"]:
            item["sha256"] = hashlib.sha256(
                (source / "vault" / item["path"]).read_bytes()).hexdigest()
        pack.write_text(json.dumps(updated), encoding="utf-8")
        apply(bundle("upstream-update"))
        assert index.read_text(encoding="utf-8") == "# User-owned index\n"
        assert private.read_text(encoding="utf-8") == "# Private choices\n"
        checks.append("upstream update preserves user index and private decisions")
        reference = shelf / "reference" / original["entrypoint"]
        reference.write_text("# Locally edited reference\n", encoding="utf-8")
        snapshot = {str(p.relative_to(vault)): p.read_bytes()
                    for p in vault.rglob("*") if p.is_file()}
        try:
            bundle("conflicting-update")
        except TransactionError:
            checks.append("local edit refuses attachment before mutation")
        else:
            raise AssertionError("Edited reference was accepted for overwrite.")
        assert snapshot == {str(p.relative_to(vault)): p.read_bytes()
                            for p in vault.rglob("*") if p.is_file()}
        print(json.dumps({"ok": True, "checks": checks, "scope": "synthetic vault only"},
                         indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
