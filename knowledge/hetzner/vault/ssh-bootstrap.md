# SSH keys and bootstrap

Sources: official servers FAQ
(`https://docs.hetzner.com/cloud/servers/faq/`) and API changelog
(`https://docs.hetzner.cloud/changelog`), observed 2026-10-09.

## Keys

- Select keys at server creation; Hetzner injects them into the new server.
- Keys cannot be added to existing servers by Hetzner; add them inside
  the OS manually (community how-to step 4:
  `https://community.hetzner.com/tutorials/howto-ssh-key`).
- Created with a key: no root credentials email. SSH by key only; Console
  by generated root password (reset on the Console Rescue page).
- Created without a key: root credentials emailed to the account main
  address only (`https://accounts.hetzner.com/account/mail`).
- Newer images set `PermitRootLogin prohibit-password`. Prefer keys.
- API rejects keys with leading whitespace (changelog 2026-04-22:
  `https://docs.hetzner.cloud/changelog#2026-04-22-ssh-key-validation`).
- Wrapper `server plan` requires at least one `--ssh-key` (name or numeric ID).

## cloud-init

- User data injected at create runs at boot. Works only with
  Hetzner-provided system images (special datasource).
- `user_data` accepted on rebuilds (2026-01-16:
  `https://docs.hetzner.cloud/changelog#2026-01-16-server-rebuild-with-user-data`).
- Private network auto-configuration via cloud-init (2026-05-18:
  `https://docs.hetzner.cloud/changelog#2026-05-18-private-network-auto-configuration-via-cloud-init`).
- Examples: `https://cloudinit.readthedocs.io/en/latest/topics/examples.html`,
  `https://help.ubuntu.com/community/CloudInit`,
  `https://community.hetzner.com/tutorials/basic-cloud-config/`.
- Wrapper plan: user data optional, max 32768 bytes, must start with
  `#cloud-config` or `#!/`; reviewed bytes snapshotted with digest, re-verified at create.
- Server Metadata is official with documented `/hetzner/v1/*` routes (API
  reference Server Metadata section). EC2-compatible routes were removed
  2026-08-01. Metadata serves user data back, so user data is visible to
  its server; never bake long-lived secrets in.
- The module ships an optional generic starting fixture,
  `cloud-init/minimal.yaml`. It carries no keys or tokens; select a
  registered key in the plan and verify image cloud-init support.

## Access after rebuild

- Created without a key: fresh root password mailed, set on first boot
  via cloud-init. Snapshot keys keep working.
- Created with a key: that key injected on first boot. Snapshot keys keep
  working.
- No old root password works right after a rebuild.
- Applies only to snapshots from officially provided images.

## Verify

Plan accepted keys; preflight passed; dry-run passed; live create (only
with explicit authorization) returned `created`; SSH with the expected
key works; cloud-init completed on the host; Console fallback is written
in the private server record (`templates/server-record.md`).
