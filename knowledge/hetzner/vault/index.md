# Hetzner Cloud reference shelf

Attached reference for module `legends-hetzner` v0.1.2. This shelf holds
generic, source-cited runbooks for agent-operated Hetzner Cloud work with
the official `hcloud` CLI. It carries no private inventories, credentials,
addresses, or customer data.

## How to use this shelf

- Start with `onboarding.md`, then `auth-contexts.md`.
- Each task runbook ends with what to record. Records belong in your own
  project locations, never in this reference copy.
- Copy a file from `templates/` into your project and fill it there. The
  shipped templates stay generic.
- When this shelf disagrees with the module recipe
  (`docs/AGENT-RECIPE.md` in the installed module) or with
  `docs/CLI-CONTRACT.json`, those module files win for wrapper syntax.
  When any of them disagree with official Hetzner docs, the official docs
  win for provider behavior.

## Contents

- `onboarding.md`: install `hcloud` on Windows, macOS, Linux; first probes.
- `auth-contexts.md`: tokens, named contexts, the wrapper auth rule.
- `ssh-bootstrap.md`: SSH keys, cloud-init, rebuild access, verification.
- `preflight.md`: immutable plans and live preflight.
- `backups-restore.md`: backups vs snapshots and restore proof.
- `coolify-boundary.md`: optional Coolify ownership boundary.
- `troubleshooting.md`: auth, SSH, plans, provider behavior, rescue.
- `limitations.md`: honest scope limits and untested items.
- `api-changes.md`: module-relevant API changes with verified links.
- `sources.md`: source ledger with observation dates.
- `templates/server-record.md`: one server, plan hash, receipt, fallback.
- `templates/preflight-checklist.md`: per-plan verification notes.
- `templates/restore-proof.md`: rehearsal evidence.
- `templates/decision-log.md`: dated decisions with sources.

## Ownership and updates

This copy is a versioned snapshot attached by the Empire knowledge engine.
Local edits to any file in this snapshot will block future pack updates
until you inspect and preserve them; there is no force-overwrite. The
shelf `index.md` one level up and everything in your project locations is
yours and is never overwritten by pack updates. The module resolver is
`cto-legends handoff legends-hetzner`.
