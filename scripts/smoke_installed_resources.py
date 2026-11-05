"""Verify installed wheel resources outside the source checkout."""
import json
from pathlib import Path
import subprocess
import sys


def main():
    completed = subprocess.run([sys.executable, "-m", "legends_hetzner", "resources"],
                               check=True, capture_output=True, text=True)
    report = json.loads(completed.stdout)
    assert report["source"] == "package_data", report
    assert report["recipe_exists"] is True, report
    assert report["pack_exists"] is True, report
    assert report["skills_cto_legends_exists"] is True, report
    assert len(report["pack_files"]) >= 16, report
    assert Path(report["recipe"]).is_file(), report
    for path in report["pack_files"]:
        assert Path(path).is_file(), path
    print(json.dumps({"ok": True, "source": report["source"], "pack_files": len(report["pack_files"])}))


if __name__ == "__main__":
    main()
