# Auth and named contexts

## Tokens

Tokens are per project, created in the Console
(`https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/`).
Never put a token in argv, plans, receipts, records, or diagnostics. Pass
live tokens only via `HCLOUD_TOKEN` or an existing named context.

## Contexts

```bash
hcloud context create <context-name>
```

Keep the name similar to the project name. Confirm flags with
`hcloud context --help` and the manual at
`https://github.com/hetznercloud/cli/tree/main/docs`.

## Wrapper rule (contract v4)

One auth source per invocation: `HCLOUD_TOKEN` xor `--context NAME`.
Both set is `AUTH_AMBIGUOUS` (exit 2). Neither on a live command is
`AUTH_MISSING` (exit 5). With `--context`, it is passed to every `hcloud`
call and `HCLOUD_TOKEN` is removed from the child environment.

Offline (no auth): `doctor`, `server plan`, `resources`. Live (explicit
auth): `doctor --live`, `inventory`, `catalog`, `server preflight`,
`server create`. Plan records the active `--context` as `planned_context`
(null in token mode); preflight and create enforce it
(`PLAN_CONTEXT_MISMATCH`, exit 2).

## Practice

One invocation per project with its own `--context`. Name the auth source
in notes, never the value. Rotate exposed tokens in the Console; the
wrapper stores nothing.
