# SPDX-License-Identifier: MIT
"""Resolve recipe and knowledge-pack paths (checkout or wheel _data)."""

from __future__ import annotations

from pathlib import Path

from . import __version__

RECIPE_REL = Path("docs") / "AGENT-RECIPE.md"
PACK_REL = Path("knowledge")
CLOUD_INIT_REL = Path("cloud-init")
SKILL_REL = Path("skills") / "cto-legends"


def _has_markers(root: Path) -> bool:
    """Module-specific checkout proof; bare docs//knowledge/ never counts."""
    try:
        if (root / "docs" / "CLI-CONTRACT.json").is_file():
            return True
        agents = root / "AGENTS.md"
        if agents.is_file():
            try:
                if "legends-hetzner" in agents.read_text(encoding="utf-8", errors="ignore"):
                    return True
            except OSError:
                pass
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8", errors="ignore")
                if "legends-hetzner" in text or "legends_hetzner" in text:
                    return True
            except OSError:
                pass
        if ((root / "docs" / "AGENT-RECIPE.md").is_file()
                and (root / "knowledge" / "hetzner" / "pack.json").is_file()):
            return True
    except OSError:
        return False
    return False


def _checkout_root() -> Path | None:
    """Checkout root only with module-specific markers."""
    root = Path(__file__).resolve().parent.parent
    try:
        return root if _has_markers(root) else None
    except OSError:
        return None


def _package_data_root() -> Path | None:
    """Installed _data dir: adjacent to the package (ordinary pip wheels)."""
    try:
        adjacent = Path(__file__).resolve().parent / "_data"
        if adjacent.is_dir():
            return adjacent
    except OSError:
        pass
    try:
        from importlib.resources import as_file, files
    except ImportError:
        return None
    try:
        ref = files("legends_hetzner._data")
    except (ImportError, ModuleNotFoundError, ValueError):
        return None
    try:
        with as_file(ref) as path:
            candidate = Path(path)
            held = candidate if candidate.is_dir() else None
    except (TypeError, ValueError, OSError, FileNotFoundError):
        return None
    try:
        return held if held is not None and held.exists() else None
    except OSError:
        return None


def _pack_files(pack_dir: Path, limit: int = 100) -> list[str]:
    if not pack_dir.is_dir():
        return []
    out: list[str] = []
    for item in sorted(pack_dir.rglob("*")):
        if item.is_file():
            out.append(str(item.resolve()))
            if len(out) >= limit:
                break
    return out


def resolve() -> dict:
    """Return absolute paths; never fails when docs are missing."""
    # Prefer installed _data when present (wheel); checkout only otherwise.
    data = _package_data_root()
    if data is not None:
        source = "package_data"
        base = data
    else:
        root = _checkout_root()
        if root is not None:
            source = "checkout"
            base = root
        else:
            source = "missing"
            base = Path(__file__).resolve().parent.parent
    recipe = (base / RECIPE_REL).resolve()
    pack_dir = (base / PACK_REL).resolve()
    cloud_init = (base / CLOUD_INIT_REL).resolve()
    skill = (base / SKILL_REL).resolve()
    return {
        "version": __version__,
        "root": str(base.resolve()),
        "recipe": str(recipe),
        "recipe_exists": recipe.is_file(),
        "pack_dir": str(pack_dir),
        "pack_exists": pack_dir.is_dir(),
        "pack_files": _pack_files(pack_dir),
        "cloud_init_dir": str(cloud_init),
        "cloud_init_exists": cloud_init.is_dir(),
        "skills_cto_legends": str(skill),
        "skills_cto_legends_exists": skill.exists(),
        "source": source,
    }
