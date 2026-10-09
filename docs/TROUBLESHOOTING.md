# Troubleshooting

Start with the narrowest failing layer: wrapper usage, auth, live state,
guest access, then provider behavior. Quote exit codes and receipt status
values exactly.

## Wrapper usage and auth

- `AUTH_AMBIGUOUS` (exit 2): both `HCLOUD_TOKEN` and `--context` are set.
  Pick one auth source for the invocation and re-run.
- `AUTH_MISSING` (exit 5): a live command ran with neither source. Provide
  `--context NAME` or export `HCLOUD_TOKEN` (one only).
- 401 or 403 from the provider: wrong token, revoked token, or a token from
  a different project. Tokens are per project. Create or re-check the token
  in the Console and update the context.
- `hcloud` not found: install per `docs/ONBOARDING.md`, or point the
  wrapper at the executable with `--hcloud-bin PATH`.
- Timeouts: the default per-call timeout is 30 seconds (`--timeout SECS`,
  range 1-120). A timeout on a create attempt is reported as uncertain,
  never as success.

## Plans and preflight

- `NEED_APPROVAL` (exit 2): live create without `--approve`. Add the flag
  only with explicit authorization for the defined scope.
- `PLAN_HASH_MISMATCH` (exit 2): the `--plan-hash` argument does not match
  the embedded plan hash. Copy the hash from the plan file exactly.
- `PLAN_TAMPERED` (exit 2): plan contents changed without a recomputed
  reviewed hash. Edits to the original user-data file do not affect the
  snapshotted plan. Make a new plan; never hand-edit a plan file.
- `PLAN_STALE` (exit 2): the plan is older than the max age (default 24
  hours). Re-plan against current live state.
- `PLAN_CONTEXT_MISMATCH` (exit 2): preflight or create ran under a
  different auth selection than planned. Re-run with the planned
  `--context` (or token mode) or make a new plan.
- Exit 3 with `failures[]`: preflight blocked, no write attempted. Fix the
  named item (name taken, type, location, image, or keys) and re-run.
- Exit 4 with `uncertain_*`: the write outcome is unknown. Do not retry
  blindly; the wrapper performs a single CLI invocation and never retries
  (upstream `hcloud` may perform internal retries). Inspect the receipt
  readback, the Console, and `inventory` before deciding the next step.

## SSH and guest access

- Key not working on an existing server: Hetzner only injects keys at
  creation and cannot add them later. Add the key inside the OS manually,
  or reach the server through the Console and a reset root password.
- No root password email: expected when the server was created with a key.
  Without a key, the email goes only to the account main address; a lost
  email is recoverable through the Console password reset.
- Root password rejected over SSH on a key-created server: newer images set
  `PermitRootLogin prohibit-password`. Use the key for SSH and the
  generated password for the Console, or change the SSH config deliberately.
- Key rejected at registration: strip leading whitespace (the API rejects
  it since 2026-04-22).
- Surprise access after a rebuild: apply the two FAQ cases in
  `docs/SSH-BOOTSTRAP.md`, and confirm the snapshot came from an official
  image.
- Two default routes or unreachable instance after network changes: the FAQ
  traces one known case to an old `hc-utils` under NetworkManager and names
  updated packages. Update guest packages before deeper diagnosis.

## Provider behavior

- Mail ports 25 and 465 are blocked by default on all cloud servers. Port
  587 through external delivery services works without a request. Unblocking
  needs a limit request after one month and the first paid invoice
  (official FAQ).
- Datacenter endpoints return 410 Gone since 2026-10-01. Use locations.
- The `deprecated` response field is removed 2026-11-02; read `deprecation`
  instead. See `docs/API-CHANGES.md`.
- EC2-compatible metadata routes (`/2009-04-04/...`, `/latest/...`) are
  removed; the native `/hetzner/v1/*` routes are the officially documented
  ones (changelog 2026-06-30). Read exact paths from the Server Metadata
  section of the API reference.
- Debian 11 images are deprecated and unavailable for new servers after
  2026-11-30. Pick a supported image.

## Rescue and console

- Rescue is a Debian-based live environment over network boot that runs in
  memory without touching disks. Use it for repairs, data access, backups,
  and OS installs (official FAQ; rescue guide, ledger source 16).
- The Console gives out-of-band access including password reset. The FAQ
  notes the VNC console keyboard is not always reliable; prefer SSH for
  real work and keep console use to recovery.

## Getting help

Hetzner support is reachable from the Console (ledger `SOURCES.md`). Include
project, server name, location, time in UTC, and the redacted error. Never
include tokens. For wrapper faults, attach the redacted receipt JSON and the
exact command with the token removed.
