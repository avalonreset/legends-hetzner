# Limitations

- Provisioning is mocked-write-only in v0.1.0. Live `server create` is
  implemented but untested against disposable resources. Do not claim live
  provisioning works.
- No wrapper commands for backups, snapshots, rebuilds, rescue,
  firewalls, networks, load balancers, DNS, volumes, images, or SSH key
  management. Use official surfaces directly.
- Facts here were researched from official sources on 2026-10-09 (see
  `sources.md`). Measured platform evidence is in `docs/VALIDATION.md`,
  including the Windows live read-only pass with real `hcloud` 1.61.0.
- Re-check `https://docs.hetzner.cloud/changelog` before release-grade
  claims. Pricing, limits, and quotas are never asserted here.
- MCP: no official MCP identified in reviewed official sources as of
  2026-10-09 (org enumeration plus web search surfaced community projects
  only). Qualified inference, not exhaustive proof. No MCP is required,
  bundled, or endorsed.
- Server Metadata is official with documented `/hetzner/v1/*` routes;
  EC2-compatible routes were removed 2026-08-01. Metadata serves user
  data back, so user data is a bootstrap channel, not a secret store.
- Pack attach: native Windows supports preview; apply needs WSL or POSIX
  with persistent permissions. No direct-write installer. Pack hashes
  prove content identity, not truth.
- This module is independent software, not an official Hetzner product.
  Coolify is optional and separately owned; the module never manages
  inside it. A passing preflight is point-in-time, not a promise.
