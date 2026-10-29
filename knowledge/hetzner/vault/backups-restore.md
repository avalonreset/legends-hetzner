# Backups, snapshots, restore proof

Sources: `https://docs.hetzner.com/cloud/servers/getting-started/enabling-backups/`
and `https://docs.hetzner.com/cloud/servers/faq/`, observed 2026-10-09.

## Backups vs snapshots

- Backups: automatic daily once enabled per server (Console Backups tab).
  Seven slots; oldest deleted when full. Backup time cannot be picked.
- Snapshots: manual; use when precise capture timing matters.
- Rebuilds re-run first-boot injection via cloud-init; the access cases
  in `ssh-bootstrap.md` apply. Snapshots must come from officially
  provided images for that behavior.
- Full reinstall: FAQ recommends delete plus recreate. Keep the public IP
  by disabling Primary IP auto-delete or detaching it first.

## Wrapper scope

v0.1.2 has no backup, snapshot, rebuild, or restore commands. Use the
Console, API, or `hcloud` directly (confirm flags with `--help`).

## Restore proof

Backup existence is not proof. Only a rehearsal proves a restore. Record
in `templates/restore-proof.md`: source id and capture time; target
server; completed rebuild action; boot plus SSH (or Console) verified;
services and data spot-checks; discrepancies with an owner.

Pricing and retention beyond the 7-slot rule are not asserted here; check
official pages at decision time and record what you found.
