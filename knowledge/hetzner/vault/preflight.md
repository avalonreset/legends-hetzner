# Plans and preflight

Wrapper syntax source of truth is `docs/CLI-CONTRACT.json` (contract v4)
in the installed module.

## Flow

1. `server plan` (offline): writes immutable
   `{plan: {...}, plan_hash: sha256:...}`, records `planned_context`, and
   snapshots reviewed user-data bytes with digest. Refuses to overwrite
   `--out`. Plans may contain plaintext bootstrap config: keep private.
2. `server preflight` (live read-only): verifies hash, planned context,
   digest, age, then name, type, location, image, keys. No writes.
3. `server create --dry-run`: full verification, no write.
4. Live create: needs `--approve` plus matching `--plan-hash`, one
   attempt and the wrapper never retries (upstream `hcloud` may perform
   internal retries). Uncertain outcomes exit nonzero with
   `uncertain_*`; never false success.

The live path has a validated disposable Windows-client canary to an
Ubuntu 24.04 server: create/readback, SSH, cloud-init and cleanup.
See the installed module's `docs/VALIDATION.md` for the bounded evidence.

## Plan rules

- At least one `--ssh-key`, name or numeric ID.
- User data max 32768 bytes, starts with `#cloud-config` or `#!/`.
  Reviewed bytes are snapshotted into the plan; original-file edits do
  not alter it. Plan-content edits without a recomputed reviewed hash
  are rejected (`PLAN_TAMPERED`, exit 2).
- Default max age 24 hours. Re-plan stale plans; never hand-edit.
- Missing `--approve` is `NEED_APPROVAL` (exit 2).

## Verify live before planning

`catalog --kind server-types|locations|images|ssh-keys` with explicit
auth, then confirm: image available and not deprecated; type exists in
the chosen location (types are per location since 2025-09-24); location
(name or ID) current (datacenter endpoints removed 2026-10-01,
410 Gone); keys (names or IDs) exist in the project. See `api-changes.md`
for the digest.

## Read the output

- `passed: true`, empty `failures`: live state currently admits the plan.
  Re-run close to create time.
- Exit 3: blocked, no write attempted. Fix the named item, re-run.
- Exit 2 plan errors (`PLAN_TAMPERED`, `PLAN_STALE`,
  `PLAN_HASH_MISMATCH`): make a new plan. `PLAN_CONTEXT_MISMATCH`:
  re-run under the planned selection or re-plan.

Keep plan hash, receipt, and labels in the private server record
(`templates/server-record.md`).
