# Knowledge pack: attach and update

The module ships an attachable Empire knowledge pack. It is a versioned
reference shelf, not a vault and not a skill.

## Pack identity

- Manifest: `knowledge/hetzner/pack.json`
- Schema: `legends.knowledge-pack/v1`
- Id: `hetzner`
- Module: `legends-hetzner`
- Version: `0.1.1`
- Entrypoint: `index.md`
- Suggested home: `wiki/library/legends-hetzner/hetzner`
- Ontology kind: `library`
- Files: declared Markdown under sibling `vault/`, each pinned by SHA-256

The manifest lists every shipped file with its hash. Changing manifest
bytes requires a new pack version.

## Ownership

| Material | Location | Update behavior |
|---|---|---|
| Released knowledge | Installed module `knowledge/hetzner/vault/` | Updated with the module |
| Attached reference snapshot | Selected Empire shelf `reference/` | Updated only when the last shipped bytes are unchanged |
| User knowledge | Shelf `index.md` plus the owner project, evidence, and session locations | Never overwritten by pack updates |

The first attachment creates a readable user-owned `index.md`, a
`reference/` snapshot, and a `pack-state.json` ledger. The workflow does
not create an empty `work/` directory; private records stay in the owner
existing locations or in templates copied there. Installing the module
never selects or modifies a vault. No implicit vault writes happen during
installation.

## Attach or update

Use the pack from the installed module. Resolve its path through the
router (`cto-legends handoff legends-hetzner`) and read the installed
recipe; paths below are the documented shape from the Empire
knowledge-packs doc (ledger source 34), so confirm
the exact engine command against the installed Empire version before use.

Preview with an explicit vault, operation id, and timestamp:

```bash
python scripts/claude-empire.py knowledge attach knowledge/hetzner/pack.json \
  --vault /path/to/Empire --operation-id attach-hetzner-001 \
  --generated-at 2026-10-09T12:00:00Z
```

Read the proposed transaction, then repeat with
`--apply --approved-plan-sha256 <reviewed-hash>` when authorized. The hash
binds the reviewed changes; it is not an independent approval policy.
`--destination wiki/library/my-chosen-shelf` selects another location under
`wiki/library/`.

Use `legends-empire` 0.3.1+ and Python 3.11+ for native Windows preview and
apply. The Windows backend supports local NTFS with stable file identities,
current-user-owned files and restorable security descriptors. It binds ACL
state into the reviewed plan and rejects unsafe path or permission changes.
Network/UNC shares, synced folders, reparse paths and unsupported security
layouts are outside this support scope. A readiness refusal is not a reason
to weaken ACLs or bypass the transaction engine.

macOS, Linux and correctly configured WSL use the POSIX backend with
persistent file permissions. Mounted Windows drives in WSL require DrvFS
metadata. Preview and apply in the same environment. Windows supports
process-crash recovery; it does not claim POSIX directory `fsync` or
equivalent power-loss durability. There is no alternate direct-write installer.

After a module update, run the same attach command with a new operation id
and the new pack. An unchanged pack returns `noop`. The module version and
the attached snapshot version can differ until this explicit update.

## Edit preservation

- Updates compare every owned reference against its last shipped hash. A
  modified or missing reference refuses the whole operation. There is no
  force-overwrite flag.
- The user-owned `index.md` is preserved across updates.
- Files removed upstream stay on disk, marked `obsolete: true` in the
  ledger. The workflow has no deletion command.
- New upstream filenames cannot overwrite unowned content. Case aliases,
  escaping paths, and symlink or junction redirects are refused.
- Index links into an existing custom ontology are a separate, reviewed
  user-note change, never an implicit install rewrite.

## Private work templates

The pack ships record templates under `vault/templates/`. Copy a template
into a user-owned location and fill it there; the shipped copy stays
generic. Templates carry placeholders only, never private names, addresses,
paths, or secrets:

- `server-record.md`: one server, plan hash, receipt, access fallback.
- `preflight-checklist.md`: per-plan live verification notes.
- `restore-proof.md`: backup and snapshot rehearsal evidence.
- `decision-log.md`: dated decisions with sources and owners.

## Release proof expectations

Pack admission checks: manifest integrity (hashes match bytes), package
inclusion, fresh attachment, repeat attachment, upstream update, locally
edited reference conflict (must fail before partial mutation), and
natural-language discovery through the router. The measured record is in
`docs/VALIDATION.md`, reproducible with `scripts/verify_knowledge_attachment.py`.
The script uses a temporary synthetic vault and checks preview without
writes, fresh attach, repeat-attach noop, update preserving user content
and local-edit conflict. It refuses native Windows with Empire older than
0.3.1. CI exercises the installed wheel's pack against an immutable pinned
Empire engine on Windows, macOS and Linux.
