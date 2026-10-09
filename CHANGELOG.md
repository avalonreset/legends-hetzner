# Changelog

## 0.1.1 — 2026-10-09

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

## 0.1.0 — 2026-10-09

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
