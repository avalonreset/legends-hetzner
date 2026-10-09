# SSH keys and bootstrap verification

Facts below come from the official servers FAQ (ledger source 11) and the
API changelog (ledger source 2), observed 2026-10-09.

## Key behavior

- Select one or more SSH keys when creating a server. Hetzner adds the
  selected keys to the new server automatically.
- Hetzner cannot add SSH keys to existing servers. For a running server,
  add the key inside the OS manually (the FAQ points to step 4 of the
  community SSH how-to, ledger source 22).
- A server created with a key receives no root credentials email. SSH access
  uses the key only. Console access uses a generated root password, which
  can be reset from the Console Rescue page ("Reset Root Password").
- A server created without a key receives root credentials by email, sent
  only to the account main address
  (`https://accounts.hetzner.com/account/mail`). A lost email is recoverable
  through the same Console password reset.
- Newer OS images disable root password login over SSH by default
  (`PermitRootLogin prohibit-password`) because of brute-force risk. The FAQ
  documents how to re-enable it; prefer keys instead.
- The API rejects SSH keys with leading whitespace characters
  (changelog 2026-04-22). Trim key material before registering it.
- The wrapper requires at least one `--ssh-key` in every `server plan`
  (contract v4, names or numeric IDs). Keyless password-only creates are
  out of scope.

## cloud-init specifics

- User data can be injected at server creation and runs at boot. The FAQ
  example is a plain script:

  ```bash
  #!/bin/bash
  touch /tmp/cloudinit_was_here
  ```

- cloud-init works only with Hetzner-provided system images, which carry a
  special cloud-init datasource. Systems installed by other means (for
  example through rescue) may not reconfigure through cloud-init.
- `user_data` is also accepted on server rebuilds (changelog 2026-01-16).
- Private network auto-configuration is available through cloud-init
  (changelog 2026-05-18).
- Upstream examples live in the cloud-init docs and the Ubuntu CloudInit
  help page (ledger sources 26 and 27, both linked from the FAQ), plus the
  Hetzner community cloud-config tutorial (ledger source 21).
- Wrapper plan rules: user-data file is optional, at most 32768 bytes, and
  must start with `#cloud-config` or `#!/`. The reviewed bytes are
  snapshotted into the plan with their SHA-256 digest and re-verified at
  create time.
- The module ships an optional generic starting fixture,
  `cloud-init/minimal.yaml` (`#cloud-config`, SSH password auth off, UTC,
  completion message). It carries no keys or tokens; select a registered
  key in the plan and verify the image supports cloud-init before use.
- Server Metadata is official: the API reference documents it with native
  `/hetzner/v1/*` routes, and the EC2-compatible routes were removed on
  2026-08-01 after deprecation on 2026-06-30 (see `docs/API-CHANGES.md`).
  Metadata serves user data back, so treat user data as visible to its
  server and never bake long-lived secrets into it.

## Access after a rebuild (official FAQ cases)

Assume `server1` was rebuilt from snapshot `snap1`:

- Case 1, `server1` was created without a key: a new root password is
  generated and mailed, and set on first boot through cloud-init. Keys
  already inside `snap1` keep working.
- Case 2, `server1` was created with key `key1`: `key1` is injected on first
  boot through cloud-init. Extra keys inside the snapshot keep working.
- In all cases, no root password works directly after the rebuild, even one
  previously set in the snapshot.
- These cases apply only to snapshots taken from officially provided
  images. Other installs may behave differently.

## Bootstrap verification checklist

1. `server plan` accepted the keys and snapshotted the user data with its digest.
2. `server preflight` passed against live state (keys exist, image valid).
3. `server create --dry-run` passed; a live create ran only with explicit
   authorization and returned a receipt with status `created`.
4. SSH with the expected key succeeded to the new server.
5. cloud-init completed on the host (check with the upstream cloud-init
   status tooling on the server itself).
6. Expected users, packages, or services from user data are present.
7. Console fallback is documented in the private server record: reset path
   and who holds access. The record template is
   `knowledge/hetzner/vault/templates/server-record.md`.

Record key names or IDs and fingerprints in private records, never private key
material.
