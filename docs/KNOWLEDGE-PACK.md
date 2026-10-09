# Knowledge pack: attach and update

The module ships an attachable Empire knowledge pack. It is a versioned
reference shelf, not a vault and not a skill.

## Pack identity

- Manifest: `knowledge/hetzner/pack.json`
- Schema: `legends.knowledge-pack/v1`
- Id: `hetzner`
- Module: `legends-hetzner`
- Version: `0.1.0`
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
knowledge-packs doc (`legends-empire` 0.3.0, ledger source 34), so confirm
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

Platform rule: native Windows supports preview. Applying uses the existing
recoverable transaction engine and requires WSL or a supported POSIX host
with persistent POSIX file permissions; Windows drives mounted in WSL need
DrvFS metadata enabled. Preview and apply in the same environment. There is
no alternate direct-write installer.

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
natural-language discovery through the router. The attachment integration
was run against Empire 0.3.0 in a WSL POSIX temporary vault and all five
scenarios passed (preview without writes, fresh attach, repeat-attach
noop, update preserving user content, local-edit conflict); the measured
record is in `docs/VALIDATION.md`, reproducible with
`scripts/verify_knowledge_attachment.py`. Attachment behavior here is
documented from the Empire engine doc (ledger source 34).
