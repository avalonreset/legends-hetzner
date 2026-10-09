# Honest limitations

What v0.1.0 does not do, what is untested, and where to check instead.

## Provisioning

- Provision support is mocked-write-only. Live `server create` is
  implemented but has no validated test against disposable resources. Do not
  claim live provisioning works until a reviewed canary (create, readback,
  cleanup) proves it.
- The wrapper has no commands for backups, snapshots, rebuilds, rescue,
  firewalls, networks, load balancers, DNS, volumes, images, or SSH key
  management in v0.1.0. Those operations stay on their official surfaces:
  Console, API, or `hcloud` directly.

## Evidence status

- The install steps, CLI behavior, and product facts in these docs were
  researched from official sources on 2026-10-09 (see `docs/SOURCES.md`).
  Measured platform evidence is in `docs/VALIDATION.md`, including the
  Windows pass with Python 3.11.7 and real `hcloud` 1.61.0 (offline and
  live readiness, inventory, all catalog reads).
- Changelog facts are current to the October 2026 entries observed. Always
  re-check `https://docs.hetzner.cloud/changelog` before release-grade
  claims.
- Pricing, limits, and quotas are deliberately not asserted anywhere in
  this module. Check the official pages at decision time.

## MCP

- No official MCP identified in reviewed official sources as of
  2026-10-09. The check listed the public repositories under the official
  `hetznercloud` organization (33 repos, none MCP-named) and searched the
  web, which surfaced only community projects (ledger sources 28-31).
  This is a qualified inference, not an exhaustive proof of absence.
  Community MCP projects are not required, bundled, or endorsed by this
  module. Agent access works through the wrapper, `hcloud`, and the API
  docs.

## Metadata and user data

- Server Metadata is official: the API reference documents it, and the
  changelog names `/hetzner/v1/*` as the officially documented routes
  (2026-06-30). Read exact paths from the Server Metadata section of the
  API reference
  (`https://docs.hetzner.cloud/reference/cloud#description/server-metadata`).
- The EC2-compatible metadata routes (`/2009-04-04/...`, `/latest/...`)
  were removed on 2026-08-01 per the official changelog. Do not build on
  them.
- Metadata serves user data back (the removed routes included user-data
  paths), so user data is visible to its server. It is a bootstrap
  channel, not a secret store.

## Knowledge attachment

- Attaching the knowledge pack needs the existing Empire transaction
  engine from `legends-empire`; it is not reimplemented here.
- Native Windows supports preview. Applying a pack needs WSL or a POSIX
  host with persistent permissions (DrvFS metadata on mounted Windows
  drives). Preview and apply in the same environment. There is no
  direct-write installer.
- Pack hashes prove content identity, not truth. Imported Markdown stays
  reference material under the owner instructions.

## Product boundaries

- The module is independent software, not an official Hetzner product, and
  is not affiliated with Hetzner (see `THIRD_PARTY_NOTICES.md`).
- Coolify is optional and separately owned; the module never manages inside
  Coolify (see `docs/COOLIFY-BOUNDARY.md`).
- Hetzner images, types, and locations change over time. A passing
  preflight is a point-in-time statement, not a durability promise.
