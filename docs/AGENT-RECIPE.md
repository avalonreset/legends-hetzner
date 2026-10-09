# `legends-hetzner` agent recipe (canonical)

Module `legends-hetzner` v0.1.0. Agent-operated Hetzner Cloud workflows that
wrap the official `hcloud` CLI with reviewed plans, read-only preflight, and
a source-cited reference library.

The only registered skill is `cto-legends`. This file is the canonical task
instruction for the module. No standalone module skill exists or is required.
No MCP server is required; see `docs/LIMITATIONS.md` for the MCP finding.

Read first, in order:

1. `docs/CLI-CONTRACT.json` (exact CLI syntax, source of truth)
2. `docs/LIMITATIONS.md` (what v0.1.0 does not do)
3. `docs/SOURCES.md` (source ledger with dates and URLs)
4. The runbook for the task at hand (list below)

## Runtime shape

- Entries: `python -m legends_hetzner` and the `legends-hetzner` console script.
- Python 3.10+ standard library only. No third-party runtime dependency.
- Provider calls go to the external `hcloud` executable via argv with
  `shell=False` and a bounded timeout. `hcloud` is an upstream prerequisite,
  never vendored.
- Provision support in v0.1.0 is mocked-write-only. Live `server create` is
  implemented but has no validated disposable-resource test. Supported use is
  mocked writes, `--dry-run`, and read-only preflight. Do not claim live
  provisioning support.

## Authentication rule (contract v4)

Exactly one auth source per invocation:

- `HCLOUD_TOKEN` environment variable, or
- `--context NAME` selecting an `hcloud` named context.

Both set is `AUTH_AMBIGUOUS` (exit 2). Neither set on a live command is
`AUTH_MISSING` (exit 5). With `--context`, the flag is passed to every
`hcloud` call and `HCLOUD_TOKEN` is removed from the child environment.
`server plan` records the active `--context` as `planned_context` (or null
in token mode); `server preflight` and `server create` enforce it and fail
with `PLAN_CONTEXT_MISMATCH` (exit 2) when the active selection differs.
Tokens never appear in argv, output, receipts, or plan files. See `docs/AUTH.md`.

Global flags: `--context NAME`, `--timeout SECS` (default 30, range 1-120),
`--hcloud-bin PATH` (default `hcloud`), `--version`.

## Commands (contract v4)

| Command | Auth | Purpose |
|---|---|---|
| `doctor` | offline | No auth. Reads `hcloud` version only. Exit nonzero when `hcloud` is missing or errored. JSON to stdout. |
| `doctor --live` | live read-only | Read-only probe via location list. JSON to stdout. |
| `inventory` | live read-only | `{"servers": [...], "count": n}` JSON to stdout. |
| `catalog [--kind all\|server-types\|locations\|images\|ssh-keys]` | live read-only | Live catalog snapshot. JSON to stdout. |
| `server plan --name NAME --type TYPE --location LOC --image IMG --ssh-key KEY [--ssh-key KEY...] [--user-data FILE] [--label k=v ...] --out FILE` | offline | Writes an immutable plan file `{plan: {...}, plan_hash: sha256:...}`. SSH key required (names or numeric IDs). Records `planned_context` and snapshots reviewed user-data bytes with digest. Refuses to overwrite `--out`. User data at most 32768 bytes and must start with `#cloud-config` or `#!/`. Plans may contain plaintext bootstrap config: keep private, no secrets. |
| `server preflight --plan FILE [--max-plan-age-hours H]` | live read-only | Verifies plan hash, planned context, digest, and age, then checks name, type, location, image, and keys. No writes. |
| `server create --plan FILE --plan-hash sha256:... --approve [--dry-run] [--receipt FILE] [--max-plan-age-hours H]` | live | Requires `--approve` plus a matching `--plan-hash`. Single CLI invocation; the wrapper never retries (upstream `hcloud` may perform internal retries). Uncertain results are reported honestly with nonzero exit. Receipts are redacted. `--dry-run` runs preflight only. |
| `resources` | offline | Resolves recipe, pack, cloud-init, and skill paths. JSON with absolute paths. |

Exit codes: 0 success (including passing dry-run; `doctor` only when
checks pass), 1 provider or adapter failure, sanitized (also offline
`doctor` with missing or errored `hcloud`), 2 usage, validation, plan, or
auth-ambiguous (includes `PLAN_TAMPERED`, `PLAN_STALE`,
`PLAN_HASH_MISMATCH`, `PLAN_CONTEXT_MISMATCH`, `NEED_APPROVAL`,
`AUTH_AMBIGUOUS`), 3 preflight blocked with no write attempted, 4 create
failed or uncertain, 5 auth missing for a live command.

If `docs/CLI-CONTRACT.json` in the checkout differs from this summary, the
contract file wins. Never invent wrapper flags.

## Standard flows

1. Onboard: `docs/ONBOARDING.md`. Install `hcloud`, run offline `doctor`,
   create a named context, run live `doctor` and a first `catalog` probe.
2. Read-only survey: `inventory`, `catalog --kind ...`. Record OS, `hcloud`
   version, wrapper version, context name (never the token), exit codes.
3. Planned server: `server plan`, then `server preflight`, then
   `server create --dry-run`, all under the same auth selection (the
   planned context is enforced). A live create additionally needs explicit owner
   authorization for a defined disposable or production scope, and the receipt
   status must be reported exactly (`created`, `failed`, or `uncertain_*`).
   Never retry a create blindly; an uncertain result needs inspection first.
4. SSH and bootstrap: `docs/SSH-BOOTSTRAP.md`. Keys are selected at creation
   and cannot be injected into existing servers by Hetzner. Verify access and
   cloud-init completion before declaring success.
5. Backups and restore: `docs/BACKUPS.md`. The wrapper has no backup or
   snapshot commands in v0.1.0; use the Console, the API, or `hcloud`
   directly, and prove restores with a rehearsal, not with backup existence.
6. Knowledge: `docs/KNOWLEDGE-PACK.md`. The attachable pack is
   `knowledge/hetzner/pack.json` (schema `legends.knowledge-pack/v1`).
   Attachment is an explicit scoped action through the existing Empire
   engine. Installation never writes to a vault implicitly.

## Runbook index

- `docs/ONBOARDING.md`: generic setup on Windows, macOS, and Linux.
- `docs/AUTH.md`: tokens, named contexts, multi-project use, token safety.
- `docs/SSH-BOOTSTRAP.md`: SSH keys, cloud-init specifics, rebuild access,
  bootstrap verification.
- `docs/PREFLIGHT.md`: plans, live preflight, image and type availability.
- `docs/BACKUPS.md`: backups vs snapshots, rebuild semantics, restore proof.
- `docs/COOLIFY-BOUNDARY.md`: optional Coolify app ownership boundary.
- `docs/TROUBLESHOOTING.md`: auth, SSH, plans, API changes, rescue, support.
- `docs/API-CHANGES.md`: recent official API changes with dates and links.
- `docs/LIMITATIONS.md`: honest scope limits and untested items.
- `docs/SOURCES.md`: every official source used, with observation dates.
- `docs/KNOWLEDGE-PACK.md`: pack identity, attach, update, ownership.

## Evidence rules

- Keep Windows, macOS, and Linux evidence distinct. Keep live reads, mocked
  writes, and untested claims distinct.
- Save receipts, plans, and user configuration outside installed sources.
- Never record tokens, private inventories, server addresses from private
  estates, or customer data in the repository or the knowledge pack.
- Quote receipt `status` values exactly; `uncertain_*` is not success.
