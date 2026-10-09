# Authentication: tokens and named contexts

## Tokens

API tokens are created per Hetzner Cloud project in the Console. Follow the
official token doc (ledger source 8). A token belongs to exactly one
project; work across projects needs one token and one context per project.

Token handling rules:

- Never place a token in argv, in a file inside the repository, in a plan
  file, in a receipt, or in diagnostics.
- Pass live tokens only through the `HCLOUD_TOKEN` environment variable or
  an existing `hcloud` named context.
- The wrapper redacts token-shaped values and truncates errors to 2000
  characters; still, inspect anything you paste before sharing it.
- Keep user configuration and runtime evidence outside installed sources.

## Named contexts

Create one context per project (official setup tutorial, ledger source 6):

```bash
hcloud context create <context-name>
```

Enter the project API token when prompted. The context is then created and
activated. Keep the context name similar to the project name so later
invocations select the right project.

Confirm available contexts and the active one with the context subcommands;
check exact flags with `hcloud context --help` against your installed
version and the command manual (ledger source 7).

## The wrapper auth rule (contract v1)

Each wrapper invocation uses exactly one auth source:

- `HCLOUD_TOKEN` in the environment, or
- `--context NAME` on the command line.

Both set at once is `AUTH_AMBIGUOUS` and exits 2 without doing work.
Neither set on a live command is `AUTH_MISSING` and exits 5. When
`--context` is selected, the wrapper passes it to every `hcloud` call in
that invocation and removes `HCLOUD_TOKEN` from the child environment, so
one invocation can never mix projects.

Offline commands (`doctor` without `--live`, `server plan`, `resources`)
need no auth. Live read-only commands (`doctor --live`, `inventory`,
`catalog`, `server preflight`) and `server create` need explicit auth every
time; there is no ambient default beyond the single selected source.

## Suggested practice

1. Start every session with offline `doctor`, then live `doctor --live`.
2. Use read-only commands (`inventory`, `catalog`, `server preflight`,
   `server create --dry-run`) before any write path.
3. Name the auth source in your notes (context name or "env token"), never
   the token value.
4. For multi-project work, run one invocation per project with its own
   `--context`, and label the evidence per project.
5. Rotate a token in the Console if it may have been exposed, then update
   the context; the wrapper stores nothing, so there is nothing else to edit.
