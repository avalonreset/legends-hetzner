# Server record: <server-name>

Copy this template into your own project location and fill it there. Never
store tokens or private key material in any record.

- Project: <hetzner-project>
- Auth source used: <context-name or "env token"> (value never recorded)
- Server: <name> | type <type> | location <location> | image <image>
- Addresses: <assigned at create; update from readback>
- SSH keys: <key-name-1>, <key-name-2>
- Labels: <k=v, ...>
- Plan file: <private path> | plan hash: <sha256:...>
- User-data digest: <sha256:... or "none">
- Preflight: <date UTC> passed=<true/false>, failures: <none or list>
- Create: <date UTC> dry-run=<pass/fail>; live receipt status:
  <dry_run / created / failed / uncertain_*>
- Receipt: <private path>
- App choice: <plain OS | coolify | other app + version notes>
- Activation/admin URL: <url or "n/a"> | admin owner: <name>
- SSH verified: <date UTC, key used> | cloud-init completed: <yes/no>
- Console fallback: <who can reset, reset path confirmed yes/no>
- Backups enabled: <yes/no> | snapshot ids: <ids>
- Notes: <anything the next agent must know>
