# legends-hetzner agent instructions

Read `docs/AGENT-RECIPE.md`, then the smallest relevant runbook in
`knowledge/hetzner/vault/`. Run offline readiness before using the CLI and
live readiness before authorized provider operations.

Never copy private inventories, credentials, machine identities or generated
operational receipts into this repository.

Use Python 3.10+ standard library for the portable runtime and the official
`hcloud` CLI for provider operations. No PowerShell dependency for public use.
Live operations require the user's actual authorization for the exact target.
Do not infer provisioning or destructive authority from installation or a
successful readiness check. Mocked tests must be identified as such.

Only `cto-legends` is a registered skill. Module instructions belong in
`docs/AGENT-RECIPE.md`; the reusable knowledge pack follows
`legends.knowledge-pack/v1`. No implicit user vault writes during installation.

Public identity: legends-hetzner. The earlier private kit is a separate
compatibility surface, not a dependency.
Keep runtime evidence and user configuration outside installed sources.
Keep Windows, macOS, Linux, live read, live canary, mocked write, and untested evidence distinct.
