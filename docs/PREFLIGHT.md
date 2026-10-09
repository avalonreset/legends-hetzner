# Plans and preflight

The wrapper separates offline intent from live verification from the single
write. Contract v4 defines the exact syntax; this runbook explains the
judgment calls.

## The flow

1. `server plan` (offline, no auth): captures name, type, location, image,
   SSH keys (names or numeric IDs), optional user data, and labels into an
   immutable plan file, records the active `--context` as `planned_context`
   (null in token mode), and snapshots the reviewed user-data bytes with
   their digest. It refuses to overwrite an existing `--out` path. Plans
   may contain plaintext bootstrap config: keep them private and secret-free.
2. `server preflight` (live read-only, explicit auth): verifies the plan
   hash, the planned context, the user-data digest, and the plan age, then
   checks the name, type, location, image, and keys against live state. It
   makes no writes and reports `{passed, checks: [...], failures: [...]}`.
3. `server create --dry-run` (live read-only behavior): runs the same
   verification the live path runs, then stops before the write.
4. Live `server create` (explicit auth, `--approve`, matching `--plan-hash`):
   one CLI invocation; the wrapper never retries (upstream `hcloud` may
   perform internal retries). Tampered, stale, or mismatched plans abort
   with no write. A failing live preflight aborts with no write. Uncertain
   outcomes (timeout, bad JSON, readback mismatch) return a nonzero exit
   with an honest `uncertain_*` receipt status, never false success.

In v0.1.0 the live step is implemented but has no validated
disposable-resource test, so supported use stops at step 3 plus mocked
writes. A live create needs explicit owner authorization for a defined
scope, and the receipt status must be quoted exactly.

## Plan rules that commonly bite

- At least one `--ssh-key` is required, as a name or numeric ID. The API
  rejects keys with leading whitespace.
- User data is optional, at most 32768 bytes, and must start with
  `#cloud-config` or `#!/`. The reviewed bytes are snapshotted into the
  plan with their digest, so editing the original file after planning does
  not alter the plan; editing plan contents without recomputing the
  reviewed hash is rejected (`PLAN_TAMPERED`, exit 2).
- Plans expire: default max age is 24 hours (`--max-plan-age-hours`
  overrides). Re-plan rather than forcing an old plan.
- The live create requires both `--approve` and `--plan-hash sha256:...`
  matching the embedded hash. Omitting approval is `NEED_APPROVAL` (exit 2).

## What to verify live before planning

Use `catalog --kind server-types|locations|images|ssh-keys` with explicit
auth and confirm:

- The image is available for new servers and not deprecated. Debian 11 is
  deprecated and unavailable for new servers after 2026-11-30; Fedora 42
  and openSUSE 15 images are already unavailable; Fedora 44 and Ubuntu
  26.04 were added 2026-05-18 (changelog; see `docs/API-CHANGES.md`).
- The server type exists in the chosen location. Server types are
  per-location since 2025-09-24, and new types arrived 2025-10-16 while old
  shared-vCPU types were deprecated.
- The location (name or numeric ID) is current. The datacenter API endpoints were removed
  on 2026-10-01 and return 410 Gone; use locations.
- The SSH keys (names or numeric IDs) exist in the target project.

## Reading preflight output

- `passed: true` with empty `failures` means the live state currently
  admits the plan. Re-run close to create time; state can change.
- Exit 3 means preflight blocked and no write was attempted. Read
  `failures[]` and fix the plan or the live state, then re-run.
- Exit 2 on a plan problem (`PLAN_TAMPERED`, `PLAN_STALE`,
  `PLAN_HASH_MISMATCH`) means the plan file itself is unusable. Make a new
  plan; do not hand-edit the old one. `PLAN_CONTEXT_MISMATCH` means the
  active auth selection differs from the planned one: re-run under the
  planned selection or make a new plan.

## Labels and naming

Names and labels are the durable handles in later troubleshooting. Use the
private server record template
(`knowledge/hetzner/vault/templates/server-record.md`) to keep the plan
hash, image, type, location, keys, and labels together with the receipt.
