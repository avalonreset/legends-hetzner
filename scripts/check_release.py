#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independent release gate for the public legends-hetzner candidate.

Stdlib only, Python 3.10+. Scans the working tree for private
fingerprints, secret files, non-portable dependencies, manifest
inconsistencies and broken relative links. Site-specific literals live
in a private fingerprints file (never published); this script embeds
only generic structural patterns.

Exit 0: no FAIL findings. Exit 1: at least one FAIL. Exit 2: usage error.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import ipaddress
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

TOOL_VERSION = "0.1.1"
FAIL = "FAIL"
WARN = "WARN"
MAX_PER_CODE_PATH = 10

SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    "build", "dist", ".tox", ".pytest_cache", ".mypy_cache",
}
SKIP_SUFFIXES = {
    ".pyc", ".pyo", ".png", ".webp", ".jpg", ".jpeg", ".gif", ".ico",
    ".zip", ".tar", ".gz", ".whl", ".exe", ".dll", ".so", ".dylib",
    ".woff", ".woff2", ".ttf", ".otf",
}
# Vendored byte-for-byte from the central router; content scans skip it
# because findings there cannot be fixed by editing this repository.
VENDOR_PREFIX = "skills/cto-legends/"


@dataclass
class Finding:
    level: str
    group: str
    code: str
    message: str
    path: str = ""

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "group": self.group,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


class Gate:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []
        self._counts: dict[tuple[str, str], int] = {}

    def add(self, level: str, group: str, code: str, message: str,
            path: Path | None = None) -> None:
        rel = ""
        if path is not None:
            try:
                rel = path.relative_to(self.root).as_posix()
            except ValueError:
                rel = path.as_posix()
        key = (code, rel)
        seen = self._counts.get(key, 0)
        if seen >= MAX_PER_CODE_PATH:
            return
        self._counts[key] = seen + 1
        if seen == MAX_PER_CODE_PATH - 1:
            message += " [further matches in this file suppressed]"
        self.findings.append(Finding(level, group, code, message, rel))

    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.level == FAIL)

    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.level == WARN)


def _is_skipped(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_DIRS for part in rel.parts)


def iter_tree_files(root: Path):
    """All regular files under root except skipped dirs and symlinks."""
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if _is_skipped(path, root):
            continue
        yield path


def iter_text_files(root: Path):
    """Text files only: skips binary suffixes and null-byte content."""
    for path in iter_tree_files(root):
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            with open(path, "rb") as handle:
                if b"\x00" in handle.read(8192):
                    continue
        except OSError:
            continue
        yield path


def read_text_quiet(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError):
        return None


# ---------------------------------------------------------------- fingerprints

DRIVE_RE = re.compile(r"(?:^|[^A-Za-z0-9_/:])([A-Za-z]:[\\/])")
# Built from fragments so this source line itself carries no flaggable path.
_HOME_USER = r"[^/\s]+"
USERS_RE = re.compile(
    r"C:[\\/]Users[\\/]" r"|/Users/" + _HOME_USER + r"/"
    r"|/home/" + _HOME_USER + r"/"
)
EMAIL_RE = re.compile(r"[\w.%+-]+@(?:gmail|googlemail)\.com\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
TSNET_RE = re.compile(r"\.ts\.net\b")
PRIVATE_ENV_RE = re.compile(r"\.empire[/\\]secrets|empire\.env\b|fleet\.env\b")
TOKEN_KV_RE = re.compile(r"HCLOUD_TOKEN\s*[:=]\s*([^\s\"']+)")
TOKEN_QUOTED_RE = re.compile(r"HCLOUD_TOKEN\s*=\s*[\"']([^\"']+)[\"']")
PRIVKEY_RE = re.compile(r"BEGIN (?:[A-Z0-9 ]* )?PRIVATE KEY")

IP_ALLOW = [
    ipaddress.ip_network("192.0.2.0/24"),      # TEST-NET-1 documentation
    ipaddress.ip_network("198.51.100.0/24"),   # TEST-NET-2 documentation
    ipaddress.ip_network("203.0.113.0/24"),    # TEST-NET-3 documentation
    ipaddress.ip_network("169.254.169.254/32"),  # cloud metadata endpoint
    ipaddress.ip_network("0.0.0.0/32"),        # bind-all idiom
]

PLACEHOLDER_PREFIXES = (
    "<", "...", "***", "xxx", "your", "paste", "change", "example", "$",
    "todo", "insert",
)


def _is_placeholder(value: str) -> bool:
    text = value.strip().strip(",;")
    if not text:
        return True
    return text.lower().startswith(PLACEHOLDER_PREFIXES)


def _ip_flagged(token: str) -> bool:
    try:
        addr = ipaddress.ip_address(token)
    except ValueError:
        return False
    if any(addr in net for net in IP_ALLOW):
        return False
    return not addr.is_global


def _declared_emails(root: Path) -> set[str]:
    """Author/maintainer emails declared by packaging metadata (allowlist)."""
    out: set[str] = set()
    email_re = re.compile(
        r"(?im)^\s*(?:email\s*=\s*|Author-email\s*:\s*)[\"']?"
        r"([^\"'\s>,;]+@[^\"'\s>,;]+)"
    )
    for name in ("pyproject.toml", "setup.cfg", "setup.py"):
        path = root / name
        text = read_text_quiet(path)
        if text:
            out.update(email_re.findall(text))
    return out


def check_fingerprints(gate: Gate) -> None:
    allowed_emails = _declared_emails(gate.root)
    for path in iter_text_files(gate.root):
        rel = path.relative_to(gate.root).as_posix()
        if rel.startswith(VENDOR_PREFIX):
            continue
        text = read_text_quiet(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            where = f"{rel}:{lineno}"
            if DRIVE_RE.search(line):
                gate.add(FAIL, "fp", "FP_DRIVE_PATH",
                         f"drive-absolute path; use portable locations ({where})",
                         path)
            if USERS_RE.search(line):
                gate.add(FAIL, "fp", "FP_USER_PROFILE",
                         f"absolute user-profile path ({where})", path)
            for found in EMAIL_RE.findall(line):
                if found in allowed_emails:
                    continue
                gate.add(FAIL, "fp", "FP_EMAIL",
                         f"personal email address ({where})", path)
            for token in IP_RE.findall(line):
                if _ip_flagged(token):
                    gate.add(FAIL, "fp", "FP_PRIVATE_IP",
                             f"non-public IP {token}; use TEST-NET docs "
                             f"ranges ({where})", path)
            if TSNET_RE.search(line):
                gate.add(FAIL, "fp", "FP_TAILNET",
                         f"tailnet DNS reference ({where})", path)
            if PRIVATE_ENV_RE.search(line):
                gate.add(FAIL, "fp", "FP_PRIVATE_ENV",
                         f"private secret-store reference ({where})", path)
            for value in TOKEN_KV_RE.findall(line):
                if not _is_placeholder(value):
                    gate.add(FAIL, "fp", "FP_TOKEN_VALUE",
                             f"token value assignment ({where})", path)
            for value in TOKEN_QUOTED_RE.findall(line):
                if not _is_placeholder(value):
                    gate.add(FAIL, "fp", "FP_TOKEN_VALUE",
                             f"quoted token value ({where})", path)
            if PRIVKEY_RE.search(line):
                gate.add(FAIL, "fp", "FP_PRIVKEY",
                         f"private key block ({where})", path)


def check_private_fingerprints(gate: Gate, patterns_path: Path) -> None:
    try:
        raw = patterns_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read fingerprints file: {exc}", file=sys.stderr)
        raise SystemExit(2)
    patterns: list[tuple[re.Pattern, str]] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "::" in stripped:
            regex, _, desc = stripped.partition("::")
            desc = desc.strip() or stripped.strip()
        else:
            regex, desc = stripped, stripped
        try:
            patterns.append((re.compile(regex.strip()), desc))
        except re.error as exc:
            print(f"error: bad regex line {lineno} in {patterns_path}: {exc}",
                  file=sys.stderr)
            raise SystemExit(2)
    for path in iter_text_files(gate.root):
        rel = path.relative_to(gate.root).as_posix()
        if rel.startswith(VENDOR_PREFIX):
            continue
        text = read_text_quiet(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for regex, desc in patterns:
                if regex.search(line):
                    gate.add(FAIL, "priv", "PRIV_SITE_MATCH",
                             f"private fingerprint ({desc}) at {rel}:{lineno}",
                             path)


# ---------------------------------------------------------------- secrets

SECRET_NAMES = (".env",)
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def check_secret_files(gate: Gate) -> None:
    for path in iter_tree_files(gate.root):
        name = path.name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            gate.add(FAIL, "secret", "SECRET_ENV_FILE",
                     "real env file must not be committed", path)
        elif name.lower().endswith(SECRET_SUFFIXES):
            gate.add(FAIL, "secret", "SECRET_KEY_FILE",
                     "key material must not be committed", path)


def check_gitignore(gate: Gate) -> None:
    path = gate.root / ".gitignore"
    text = read_text_quiet(path)
    if text is None:
        gate.add(FAIL, "secret", "GITIGNORE_MISSING",
                 ".gitignore is required to block secret commits", path)
        return
    active = [ln.strip() for ln in text.splitlines()
              if ln.strip() and not ln.strip().startswith("#")
              and not ln.strip().startswith("!")]
    for token in (".env", ".pem", ".key"):
        if not any(token in ln for ln in active):
            gate.add(FAIL, "secret", "GITIGNORE_GAP",
                     f".gitignore does not cover {token}", path)


# ---------------------------------------------------------------- powershell

PS1_SUFFIXES = (".ps1", ".psm1", ".psd1")
PWSH_RE = re.compile(r"pwsh\s+-[A-Za-z]|powershell(\.exe)?\s+-[A-Za-z]")
PS1_CONTENT_RE = re.compile(r"[\w/\\.-]+\\." + "ps1" + r"\b")


def check_powershell(gate: Gate) -> None:
    for path in iter_tree_files(gate.root):
        if path.suffix.lower() in PS1_SUFFIXES:
            gate.add(FAIL, "psh", "PS1_FILE",
                     "PowerShell module scripts are not portable", path)
    for path in iter_text_files(gate.root):
        rel = path.relative_to(gate.root).as_posix()
        if rel.startswith(VENDOR_PREFIX):
            continue
        text = read_text_quiet(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if PWSH_RE.search(line):
                gate.add(FAIL, "psh", "PSH_INVOKE",
                         f"PowerShell invocation at {rel}:{lineno}", path)
            if PS1_CONTENT_RE.search(line):
                gate.add(FAIL, "psh", "PSH_SCRIPT_REF",
                         f"PowerShell script reference at {rel}:{lineno}",
                         path)


# ---------------------------------------------------------------- python floor

def python_files(root: Path):
    for path in iter_tree_files(root):
        if path.suffix.lower() == ".py":
            yield path


def check_py310_grammar(gate: Gate) -> None:
    for path in python_files(gate.root):
        text = read_text_quiet(path)
        if text is None:
            continue
        try:
            ast.parse(text, filename=path.name, feature_version=(3, 10))
        except SyntaxError as exc:
            gate.add(FAIL, "py", "PY310_GRAMMAR",
                     f"not Python 3.10 grammar (line {exc.lineno}: "
                     f"{exc.msg})", path)


def stdlib_scope_files(root: Path) -> list[Path]:
    files: list[Path] = []
    pkg = root / "legends_hetzner"
    if pkg.is_dir():
        files.extend(sorted(pkg.rglob("*.py")))
    for extra in ("scripts/check_release.py",):
        candidate = root / extra
        if candidate.is_file():
            files.append(candidate)
    files.extend(sorted((root / "tests").glob("test_portability*.py")))
    return [p for p in files
            if not p.is_symlink() and not _is_skipped(p, root)]


def check_stdlib_only(gate: Gate) -> None:
    names = getattr(sys, "stdlib_module_names", None)
    if names is None:
        gate.add(WARN, "py", "STDLIB_UNKNOWN",
                 "cannot enumerate stdlib on this interpreter; skipped")
        return
    base_allowed = set(names) | {"legends_hetzner", "__future__"}
    # Tooling probes tomllib (stdlib since 3.11) and then optional tomli,
    # catching ImportError and falling back to a bounded section parser.
    # Neither is required on Python 3.10; runtime imports remain strict.
    tooling_extra = {"tomli", "tomllib"}
    for path in stdlib_scope_files(gate.root):
        try:
            rel = path.relative_to(gate.root).as_posix()
        except ValueError:
            rel = ""
        allowed = base_allowed
        if not rel.startswith("legends_hetzner/"):
            allowed = base_allowed | tooling_extra
        text = read_text_quiet(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=path.name)
        except SyntaxError:
            continue  # reported by the grammar check
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in allowed:
                        gate.add(FAIL, "py", "NON_STDLIB_IMPORT",
                                 f"import {top} is not stdlib "
                                 f"(line {node.lineno})", path)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # intra-package relative import
                top = (node.module or "").split(".")[0]
                if top and top not in allowed:
                    gate.add(FAIL, "py", "NON_STDLIB_IMPORT",
                             f"from {top} import ... is not stdlib "
                             f"(line {node.lineno})", path)


def check_no_shell(gate: Gate) -> None:
    """Runtime must use argv lists only (literal shell=True / os.system)."""
    pkg = gate.root / "legends_hetzner"
    if not pkg.is_dir():
        return
    for path in sorted(pkg.rglob("*.py")):
        if path.is_symlink() or _is_skipped(path, gate.root):
            continue
        text = read_text_quiet(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=path.name)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True):
                    gate.add(FAIL, "py", "SHELL_TRUE",
                             f"shell=True subprocess (line {node.lineno})",
                             path)
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == "system"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"):
                gate.add(FAIL, "py", "OS_SYSTEM",
                         f"os.system call (line {node.lineno})", path)


# ---------------------------------------------------------------- manifest

def _project_section(text: str, section: str) -> str:
    """Raw lines of one [section] header block (regex fallback parser)."""
    out: list[str] = []
    active = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            active = stripped == f"[{section}]"
            continue
        if active:
            out.append(line)
    return "\n".join(out)


def _pyproject_scripts(root: Path) -> dict[str, str]:
    """Console entry map from pyproject (tomllib, else section scan)."""
    path = root / "pyproject.toml"
    text = read_text_quiet(path)
    if text is None:
        return {}
    tomllib = None
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            tomllib = None
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
        except Exception:
            data = {}
        scripts = (data.get("project") or {}).get("scripts") or {}
        if isinstance(scripts, dict):
            return {str(k): str(v) for k, v in scripts.items()}
    found: dict[str, str] = {}
    section = _project_section(text, "project.scripts")
    for match in re.finditer(r"([\w.-]+)\s*=\s*[\"']([^\"']+)[\"']", section):
        found[match.group(1)] = match.group(2)
    return found


def _top_level_names(path: Path) -> set[str]:
    text = read_text_quiet(path)
    if text is None:
        return set()
    try:
        tree = ast.parse(text, filename=path.name)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target,
                                                            ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _resolve_entry(root: Path, target: str) -> str | None:
    """Return an error string when 'pkg.mod:attr' does not resolve."""
    if ":" not in target:
        return f"malformed entry target {target!r}"
    modname, _, attr = target.partition(":")
    if not modname or not attr or not attr.isidentifier():
        return f"malformed entry target {target!r}"
    rel = Path(*modname.split("."))
    candidate = root / (rel.as_posix() + ".py")
    package_init = root / rel / "__init__.py"
    if candidate.is_file():
        module_path = candidate
    elif package_init.is_file():
        module_path = package_init
    else:
        return f"module {modname} has no source file"
    if attr not in _top_level_names(module_path):
        return f"{modname} defines no top-level {attr}"
    return None


def _check_pack_files(gate: Gate, pack_manifest: Path, pack: dict) -> None:
    if pack.get("schema") != "legends.knowledge-pack/v1":
        gate.add(FAIL, "manifest", "PACK_SCHEMA",
                 "pack schema must be legends.knowledge-pack/v1",
                 pack_manifest)
    if pack.get("module") != "legends-hetzner":
        gate.add(FAIL, "manifest", "PACK_MODULE",
                 "pack module must be legends-hetzner", pack_manifest)
    pack_dir = pack_manifest.parent
    vault = pack_dir / "vault"
    files = pack.get("files")
    if not isinstance(files, list) or not files:
        gate.add(FAIL, "manifest", "PACK_FILES",
                 "pack manifest lists no files", pack_manifest)
        files = []

    def _resolve(entry: str) -> Path | None:
        first = vault / entry
        if first.is_file():
            return first
        second = pack_dir / entry
        if second.is_file():
            return second
        return None

    entrypoint = pack.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint:
        gate.add(FAIL, "manifest", "PACK_ENTRYPOINT",
                 "pack manifest needs an entrypoint file", pack_manifest)
    elif _resolve(entrypoint) is None:
        gate.add(FAIL, "manifest", "PACK_ENTRYPOINT",
                 f"pack entrypoint missing: {entrypoint}", pack_manifest)
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            continue
        entry = item.get("path")
        want = item.get("sha256")
        if not isinstance(entry, str) or not entry:
            gate.add(FAIL, "manifest", "PACK_FILES",
                     "pack file entry without a path", pack_manifest)
            continue
        if Path(entry).is_absolute() or ".." in Path(entry).parts:
            gate.add(FAIL, "manifest", "PACK_PATH_ESCAPE",
                     f"pack path escapes the pack dir: {entry}",
                     pack_manifest)
            continue
        target = _resolve(entry)
        if target is None:
            gate.add(FAIL, "manifest", "PACK_FILE_MISSING",
                     f"pack file missing: {entry}", pack_manifest)
            continue
        try:
            seen.add(target.relative_to(pack_dir).as_posix())
        except ValueError:
            pass
        if not isinstance(want, str) or not re.fullmatch(r"[0-9a-f]{64}",
                                                         want):
            gate.add(FAIL, "manifest", "PACK_HASH",
                     f"pack file has no sha256: {entry}", pack_manifest)
            continue
        try:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            gate.add(FAIL, "manifest", "PACK_FILE_MISSING",
                     f"pack file unreadable: {entry}", pack_manifest)
            continue
        if actual != want:
            gate.add(FAIL, "manifest", "PACK_HASH_MISMATCH",
                     f"pack file hash mismatch: {entry}", pack_manifest)
    if vault.is_dir():
        for extra in sorted(vault.rglob("*")):
            if not extra.is_file() or extra.is_symlink():
                continue
            try:
                rel = extra.relative_to(pack_dir).as_posix()
            except ValueError:
                continue
            if rel not in seen:
                gate.add(WARN, "manifest", "PACK_UNLISTED",
                         f"vault file not in manifest: {rel}", extra)


def check_manifest(gate: Gate) -> None:
    root = gate.root
    pyproject = root / "pyproject.toml"
    text = read_text_quiet(pyproject)
    if text is None:
        gate.add(FAIL, "manifest", "NO_PYPROJECT",
                 "pyproject.toml is required", pyproject)
        return
    project = _project_section(text, "project")
    req = re.search(r"requires-python\s*=\s*[\"']([^\"']+)[\"']", project)
    if not req:
        gate.add(FAIL, "manifest", "REQ_PYTHON_MISSING",
                 "requires-python floor is required", pyproject)
    else:
        spec = req.group(1)
        matched = re.search(r"(>=|>)\s*3\.(\d+)", spec)
        ok = False
        if matched:
            op, minor = matched.group(1), int(matched.group(2))
            ok = (op == ">=" and minor >= 10) or (op == ">" and minor >= 9)
        if ok:
            pass
        elif matched:
            gate.add(FAIL, "manifest", "REQ_PYTHON_FLOOR",
                     f"requires-python {spec} is below the 3.10 floor",
                     pyproject)
        else:
            gate.add(WARN, "manifest", "REQ_PYTHON_UNPARSED",
                     f"cannot parse requires-python {spec!r}", pyproject)
    # Any license declaration form is accepted (PEP 639 SPDX
    # expressions included); build validity is proven by real
    # wheel/sdist builds, not by this gate's local setuptools.
    if not re.search(r"(?m)^\s*license", project):
        gate.add(FAIL, "manifest", "LICENSE_MISSING",
                 "project.license declaration is required", pyproject)
    # Version consistency across packaging, runtime and contract.
    versions: dict[str, str] = {}
    ver = re.search(r"(?m)^version\s*=\s*[\"']([^\"']+)[\"']", project)
    if ver:
        versions["pyproject"] = ver.group(1)
    init = root / "legends_hetzner" / "__init__.py"
    if not (root / "legends_hetzner").is_dir() or not init.is_file():
        gate.add(FAIL, "manifest", "PKG_MISSING",
                 "legends_hetzner package directory is required", init)
    else:
        src = read_text_quiet(init) or ""
        match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", src)
        if match:
            versions["package"] = match.group(1)
    contract_path = root / "docs" / "CLI-CONTRACT.json"
    contract = _load_json(contract_path)
    if isinstance(contract, dict) and contract.get("version"):
        versions["contract"] = str(contract.get("version"))
    if len(set(versions.values())) > 1:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(versions.items()))
        gate.add(FAIL, "manifest", "VERSION_SKEW",
                 f"version mismatch: {detail}", pyproject)
    for name, target in sorted(_pyproject_scripts(root).items()):
        problem = _resolve_entry(root, target)
        if problem:
            gate.add(FAIL, "manifest", "ENTRY_UNRESOLVED",
                     f"console entry {name} -> {target}: {problem}",
                     pyproject)
    if isinstance(contract, dict):
        for entry in contract.get("entries") or []:
            if not isinstance(entry, str):
                continue
            mod = re.fullmatch(r"python -m ([\w.]+)", entry.strip())
            if mod:
                modpath = root / Path(*mod.group(1).split("."))
                if not (modpath / "__main__.py").is_file():
                    gate.add(FAIL, "manifest", "CONTRACT_ENTRY_MISSING",
                             f"contract entry {entry!r} has no __main__.py",
                             contract_path)
                continue
            arrow = re.fullmatch(r"\S+\s*->\s*([\w.]+:\w+)", entry.strip())
            if arrow:
                problem = _resolve_entry(root, arrow.group(1))
                if problem:
                    gate.add(FAIL, "manifest", "CONTRACT_ENTRY_MISSING",
                             f"contract entry {entry!r}: {problem}",
                             contract_path)
    # Source-distribution manifest references.
    manifest = root / "MANIFEST.in"
    manifest_text = read_text_quiet(manifest)
    if manifest_text is None:
        gate.add(WARN, "manifest", "MANIFEST_MISSING",
                 "MANIFEST.in is expected for sdist coverage", manifest)
    else:
        for line in manifest_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if parts[0] == "include":
                for name in parts[1:]:
                    if not (root / name).exists():
                        gate.add(FAIL, "manifest",
                                 "MANIFEST_INCLUDE_MISSING",
                                 f"MANIFEST.in includes missing {name}",
                                 manifest)
            elif parts[0] in ("recursive-include", "graft"):
                if len(parts) < 2 or not (root / parts[1]).is_dir():
                    gate.add(WARN, "manifest", "MANIFEST_DIR_MISSING",
                             f"MANIFEST.in references missing dir "
                             f"{parts[1] if len(parts) > 1 else '?'}",
                             manifest)
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        if not (root / name).is_file():
            gate.add(FAIL, "manifest", "RESOURCE_FILE_MISSING",
                     f"{name} is required (wheel resources + sdist)",
                     root / name)
    # JSON payloads must parse.
    for folder in ("docs", "knowledge", "assets"):
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.json")):
            if path.is_symlink() or _is_skipped(path, root):
                continue
            if _load_json(path) is None:
                gate.add(FAIL, "manifest", "JSON_INVALID",
                         "invalid JSON payload", path)
    if not (root / "docs" / "AGENT-RECIPE.md").is_file():
        gate.add(FAIL, "manifest", "RECIPE_MISSING",
                 "docs/AGENT-RECIPE.md is required", root / "docs")
    pack_manifest = root / "knowledge" / "hetzner" / "pack.json"
    pack = _load_json(pack_manifest)
    if not pack_manifest.is_file():
        gate.add(FAIL, "manifest", "PACK_MANIFEST_MISSING",
                 "knowledge/hetzner/pack.json is required", pack_manifest)
    elif pack is None:
        pass  # corrupt JSON already reported by JSON_INVALID
    elif not isinstance(pack, dict):
        gate.add(FAIL, "manifest", "PACK_SCHEMA",
                 "pack manifest must be a JSON object", pack_manifest)
    else:
        _check_pack_files(gate, pack_manifest, pack)
    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    workflows += sorted((root / ".github" / "workflows").glob("*.yaml"))
    if not workflows:
        gate.add(FAIL, "manifest", "WORKFLOW_MISSING",
                 ".github/workflows needs at least one workflow",
                 root / ".github" / "workflows")
    skills = root / "skills"
    if not (skills / "cto-legends" / "SKILL.md").is_file():
        gate.add(WARN, "manifest", "SKILL_MISSING",
                 "skills/cto-legends/SKILL.md vendoring expected")
    if skills.is_dir():
        for candidate in sorted(skills.glob("*/SKILL.md")):
            if candidate.parent.name != "cto-legends":
                gate.add(FAIL, "manifest", "SKILL_NON_CANONICAL",
                         "only the central cto-legends skill may register; "
                         "module instructions belong in docs/", candidate)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- links

LINK_RE = re.compile(r"\]\(([^)]*)\)")


def check_links(gate: Gate) -> None:
    for path in iter_text_files(gate.root):
        if path.suffix.lower() != ".md":
            continue
        rel = path.relative_to(gate.root).as_posix()
        if rel.startswith(VENDOR_PREFIX):
            continue
        text = read_text_quiet(path)
        if text is None:
            continue
        for match in LINK_RE.finditer(text):
            target = match.group(1).strip().strip("<>")
            if not target or target.startswith("#"):
                continue
            if "://" in target or target.startswith("mailto:"):
                continue
            target, _, _frag = target.partition("#")
            target = target.strip()
            if not target:
                continue
            if target.startswith("/"):
                gate.add(WARN, "link", "LINK_ABSOLUTE",
                         f"site-rooted link {target} is not portable", path)
                continue
            if not (path.parent / target).exists():
                gate.add(FAIL, "link", "LINK_BROKEN",
                         f"relative link target missing: {target}", path)


# ---------------------------------------------------------------- assets

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ASSET_SPECS = {
    "assets/banner.png": (4096, 1024, None),
    "assets/preview.png": (1024, 256, None),
    "assets/social-preview.png": (1280, 640, 1_000_000),
}


def _png_dims(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()[:32]
    except OSError:
        return None
    if len(data) < 24 or not data.startswith(PNG_MAGIC):
        return None
    try:
        width, height = struct.unpack(">II", data[16:24])
    except struct.error:
        return None
    return (width, height)


def check_assets(gate: Gate) -> None:
    for name, (width, height, max_bytes) in ASSET_SPECS.items():
        path = gate.root / name
        if not path.is_file():
            gate.add(FAIL, "asset", "ASSET_MISSING",
                     "required release artwork is missing", path)
            continue
        dims = _png_dims(path)
        if dims is None:
            gate.add(WARN, "asset", "ASSET_UNPARSED",
                     "cannot parse PNG header", path)
            continue
        if dims != (width, height):
            gate.add(FAIL, "asset", "ASSET_DIMS",
                     f"expected {width}x{height}, found "
                     f"{dims[0]}x{dims[1]}", path)
        if max_bytes is not None and path.stat().st_size > max_bytes:
            gate.add(FAIL, "asset", "ASSET_SIZE",
                     f"exceeds {max_bytes} bytes", path)


# ---------------------------------------------------------------- main

def run_all(root: Path, fingerprints: Path | None = None) -> Gate:
    gate = Gate(root)
    check_fingerprints(gate)
    if fingerprints is not None:
        check_private_fingerprints(gate, fingerprints)
    check_secret_files(gate)
    check_gitignore(gate)
    check_powershell(gate)
    check_py310_grammar(gate)
    check_stdlib_only(gate)
    check_no_shell(gate)
    check_manifest(gate)
    check_links(gate)
    check_assets(gate)
    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independent release gate for legends-hetzner.")
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parent.parent,
                        help="repository root to scan")
    parser.add_argument("--fingerprints", type=Path, default=None,
                        help="private site-pattern file (never published)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--strict", action="store_true",
                        help="warnings also fail")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    gate = run_all(root, args.fingerprints)
    fails = gate.fail_count()
    warns = gate.warn_count()
    if args.format == "json":
        payload = {
            "tool": "check_release",
            "tool_version": TOOL_VERSION,
            "root": root.as_posix(),
            "fail": fails,
            "warn": warns,
            "findings": [f.as_dict() for f in gate.findings],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for item in sorted(gate.findings,
                           key=lambda f: (f.level != FAIL, f.code, f.path,
                                          f.message)):
            where = f" [{item.path}]" if item.path else ""
            print(f"{item.level} {item.group}/{item.code}: "
                  f"{item.message}{where}")
        print(f"check_release: {fails} FAIL, {warns} WARN "
              f"(excluded content scans: {VENDOR_PREFIX})")
    if fails:
        return 1
    if warns and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
