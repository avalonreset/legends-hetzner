# Troubleshooting

Work from the narrowest failing layer outward. Quote exit codes and
receipt statuses exactly.

## Auth and usage

- `AUTH_AMBIGUOUS` (exit 2): both token and `--context` set. Pick one.
- `AUTH_MISSING` (exit 5): live command with neither. Provide one.
- 401/403: wrong, revoked, or cross-project token. Tokens are per project.
- `hcloud` not found: install per `onboarding.md` or use `--hcloud-bin`.
- Timeouts default 30s (`--timeout` 1-120). A create timeout is uncertain,
  never success.

## Plans

- `NEED_APPROVAL`, `PLAN_HASH_MISMATCH`, `PLAN_TAMPERED`, `PLAN_STALE`
  (exit 2): fix approval, hash, or make a new plan. Never hand-edit plans.
  `PLAN_CONTEXT_MISMATCH`: re-run under the planned selection or re-plan.
- Exit 3: preflight blocked, nothing written. Fix `failures[]`, re-run.
- Exit 4 `uncertain_*`: do not retry blindly. Inspect receipt, Console,
  and `inventory` first. The wrapper performs a single CLI invocation and
  never retries (upstream `hcloud` may perform internal retries).

## SSH and guest

- Key fails on an existing server: keys inject at creation only. Add
  inside the OS or use Console plus reset password.
- No password email: expected with a key. Without a key it goes to the
  account main address only.
- Password rejected over SSH: newer images set
  `PermitRootLogin prohibit-password`. Key for SSH, generated password
  for Console.
- Key rejected at registration: strip leading whitespace (API rule since
  2026-04-22).
- Rebuild access surprises: see the two cases in `ssh-bootstrap.md`.

## Provider

- Mail ports 25/465 blocked by default; 587 works without a request.
  Unblock needs a limit request after one month plus first paid invoice.
- Datacenter endpoints: 410 Gone since 2026-10-01. Use locations.
- `deprecated` field removed 2026-11-02; read `deprecation`.
- Debian 11 unavailable for new servers after 2026-11-30.
- Rescue: Debian-based PXE live environment, runs in memory. Console is
  for recovery; its VNC keyboard is not always reliable per the FAQ.

## Help

Hetzner support via the Console with project, server, location, UTC time,
and the redacted error. Never tokens. Wrapper faults: attach the redacted
receipt and the exact command with the token removed.
