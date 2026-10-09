# Backups, snapshots, and restore proof

Official behavior comes from the backups guide and the servers FAQ (ledger
sources 11 and 12), observed 2026-10-09.

## Backups vs snapshots

- Backups are automatic and daily once enabled per server. Enable them in
  the Console on the server Backups tab. Each server has seven backup
  slots; when all slots are full, the oldest backup is deleted.
- Backup time cannot be picked. Hetzner removed that choice to spread backup
  load through the day.
- Snapshots are manual. Use a snapshot when precise control over capture
  time matters.
- Rebuilds from backups and snapshots re-run first-boot injection through
  cloud-init. The access cases in `docs/SSH-BOOTSTRAP.md` apply: a server
  created with a key gets that key injected, a server created without one
  gets a fresh mailed root password, and no old root password works right
  after the rebuild. Snapshots from officially provided images are required
  for this behavior.
- For a full reinstall, the FAQ recommends deleting the server and creating
  a new one so all settings are current. Keep the public IP by disabling
  auto-delete on the Primary IP or detaching it before deletion.

## Wrapper scope in v0.1.1

The wrapper has no backup, snapshot, rebuild, or restore commands. Perform
those operations in the Console, through the API, or with `hcloud`
directly, and keep the evidence in private records. Confirm exact `hcloud`
flags with `--help` and the command manual (ledger source 7).

## Restore proof checklist

Backup existence is not restore proof. A restore is proven only by a
rehearsal with this evidence, recorded in the private restore-proof template
(`knowledge/hetzner/vault/templates/restore-proof.md`):

1. Source identified: backup or snapshot id, server it came from,
   capture time.
2. Target identified: rebuilt or recreated server name, image, type,
   location.
3. Rebuild or recreate action completed in the Console or API with no
   error.
4. Server booted; SSH access verified with the expected key, or console
   access verified with a reset password.
5. Expected services respond; data spot-checks pass.
6. Discrepancies and follow-ups are written down with an owner.

## Cost and retention notes

Retention follows the 7-slot rule above. Current pricing for backups and
snapshots is deliberately not asserted here; check the official pricing and
product docs at the time of the decision and record what you found.
