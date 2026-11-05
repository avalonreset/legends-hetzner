# Changelog

## 0.1.4 - 2026-11-05

- Add symlink refusal (`is_symlink()`) across `--out`, `--plan`, `--user-data`, and `--receipt` file paths (`CWE-59`) with unit test coverage.
- Add `.legends-module`, `docs/router-provenance.json`, `assets/manifest.json`, and `scripts/smoke_installed_resources.py` to match the CTO Legends ecosystem module contract.
- Upgrade `scripts/check_release.py`, `AGENTS.md`, and `docs/AGENT-RECIPE.md` with Windows Defender / EDR anti-ransomware guardrails, raster metadata verification, and em/en-dash enforcement.
- Pin `avalonreset/legends-empire` `v0.3.4` (`1ede96ad670b60b215b66457369691da6c61d017`) in `.github/workflows/checks.yml`.

## 0.1.3 - 2026-10-31

- Add `legends-hetzner radar` for read-only Cost-Optimized (`CX`/`CAX`) stock sweeps across `fsn1`, `nbg1`, and `hel1`, Fractional CTO tier ranking (`cx43` -> `cx33` -> `cx23` -> `cx53`), and rate-limit-safe watch polling (`--interval >= 30`s with random jitter and bounded `--max-polls`).
- Add `legends-hetzner server snipe` to watch capacity for a reviewed, hash-pinned plan at safe jittered intervals (`>= 30`s), fail fast on any non-capacity preflight issue, and execute at most one `hcloud server create` invocation when confirmed `available=true` stock opens.
- Add automatic read-only REST server-type availability enrichment (`GET /v1/server_types`) when running against older `hcloud` binaries (such as `1.61.0`) that omit `locations[].available` and `category` from `hcloud server-type list -o json`.
- Ship Fractional CTO hardware selection and sniping documentation in `docs/CTO-SIZING-AND-SNIPING.md` and `knowledge/hetzner/vault/cto-sizing-and-sniping.md` covering `x86` (`CX`) vs `ARM64` (`CAX`), European `eu-central` budget locations, the `CX23` -> `CX33` -> `CX43` -> `CX53` ladder, 4 GB swapfile guidance for starter seats, single-box consolidation, and in-place rescale rules.

## 0.1.2 - 2026-10-29

- Raise minimum supported Python runtime to Python 3.11 (`requires-python = ">=3.11"`) across package metadata, offline `doctor` checks, `scripts/check_release.py`, knowledge pack docs, and multi-OS CI.
- Harden `.github/workflows/checks.yml` with 40-character commit SHA action pins and upgrade `pip>=26.2.2` before package installation.

## 0.1.1 - 2026-10-09

- Record the disposable live provisioning canary: a Windows client created
  an Ubuntu 24.04 server, verified readback, SSH and cloud-init, then
  removed the canary resources and temporary private key.
- Replace provisional write-support labels with the precise validated
  scope; provider execution behavior is unchanged.
- Add a reproducible canary procedure with identity-checked cleanup and
  explicit SSH host-key verification limits.
- Refresh the versioned knowledge reference pack.
- Enable the optional attachment acceptance check for native Windows with
  Empire 0.3.1+, and exercise the installed wheel's pack on all three
  operating systems in a separate Python 3.11 CI matrix.

## 0.1.0 - 2026-10-09

First public release as **legends-hetzner**.

- Portable Python 3.10+ runtime over the external official `hcloud` CLI.
- Offline readiness, explicit authentication, live inventory and catalog.
- Content-hashed server plans, read-only preflight and guarded creation.
- Source-cited onboarding, SSH, backups and troubleshooting references.
- Optional versioned Empire knowledge pack with user-edit preservation.
- One shared `cto-legends` skill and an on-demand module recipe.

Live server creation is experimental: offline mutation tests do not prove a
successful disposable-server lifecycle. See [validation](docs/VALIDATION.md)
for the precise tested scope.
