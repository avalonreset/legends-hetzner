<a name="legends-hetzner"></a>

# ![legends-hetzner](assets/banner.webp)

[![release](https://img.shields.io/github/v/release/avalonreset/legends-hetzner?sort=date&style=flat-square&label=release&labelColor=000000&color=ff0000)](https://github.com/avalonreset/legends-hetzner/releases/latest)
[![checks](https://github.com/avalonreset/legends-hetzner/actions/workflows/checks.yml/badge.svg)](https://github.com/avalonreset/legends-hetzner/actions/workflows/checks.yml)
[![license](https://img.shields.io/github/license/avalonreset/legends-hetzner?style=flat-square&label=license&labelColor=000000&color=666666)](LICENSE)

Agent-operated Hetzner Cloud workflows using the official `hcloud` CLI, with
reviewed provisioning plans and a source-cited knowledge library. Inspect a
project, check the current catalog, prepare a server plan, and give the next
agent the same documented procedure.

The runtime uses Python 3.10+ and works without PowerShell. Hetzner credentials
are needed only for live provider operations. The Markdown library remains
readable without an agent, a running service, or an Empire vault.

## What it adds

| Workflow | Module behavior |
| --- | --- |
| Readiness | Distinguishes local CLI readiness from a live API check. |
| Inventory and catalog | Reads structured provider data using an explicit token or named context. |
| Server planning | Writes a reviewable plan with a content hash, selected SSH keys, and a digest of optional user data. |
| Preflight | Rechecks the proposed resources and server name before a requested create operation. |
| Creation | Requires explicit approval and the reviewed plan hash; reports uncertain outcomes rather than treating a timeout as proof that nothing happened. |
| Knowledge | Ships setup, SSH, operations and troubleshooting references with an optional Empire attachment manifest. |

This is a focused operator workflow, not coverage of every Hetzner API.
It does not administer Robot bare-metal servers, automatically migrate apps,
manage billing, or replace infrastructure-as-code reconciliation.

## Install with your agent

The shared [cto-legends](https://github.com/avalonreset/cto-legends) router
discovers modules before they are installed:

```console
cto-legends sync
cto-legends sync --apply
cto-legends install legends-hetzner
cto-legends install legends-hetzner --apply
cto-legends handoff legends-hetzner
cto-legends run legends-hetzner -- doctor
```

The first install command previews the operation; the second installs it.
The agent reads the module recipe through `handoff`. Only the central
`cto-legends` skill is registered. No additional host skill is required.

The separate official [`hcloud` CLI](https://github.com/hetznercloud/cli)
must be installed using its documented Windows, macOS or Linux instructions.
This module never silently installs or upgrades it.

For standalone use, install the wheel from the
[release](https://github.com/avalonreset/legends-hetzner/releases/latest) into
a virtual environment, or install the tagged source:

```console
python -m pip install "git+https://github.com/avalonreset/legends-hetzner.git@v0.1.0"
legends-hetzner doctor
legends-hetzner resources
```

`resources` locates the recipe and knowledge pack, including in a wheel
installation outside a Git checkout. On systems where Python is named
`python3`, use that command instead.

## First useful workflow

Configure a named project context using the official CLI's interactive setup:

```console
hcloud context create my-project
legends-hetzner --context my-project doctor --live
legends-hetzner --context my-project inventory
legends-hetzner --context my-project catalog
```

Alternatively, provide `HCLOUD_TOKEN` through your environment or secret
manager. Do not combine it with `--context`; the module rejects ambiguous
authentication. It does not search personal vaults for credentials.

Prepare a plan using a type, location, image and existing SSH key from the
current catalog:

```console
legends-hetzner --context my-project server plan --name example-app --type TYPE --location LOCATION --image IMAGE --ssh-key KEY --out ./server-plan.json
legends-hetzner --context my-project server preflight --plan ./server-plan.json
```

Replace the uppercase placeholders before running. Review the plan and its
printed hash, then check the proposed create without making the purchase:

```console
legends-hetzner --context my-project server create --plan ./server-plan.json --plan-hash sha256:REVIEWED_HASH --approve --dry-run
```

Removing `--dry-run` requests a paid creation. Live creation is an experimental
path in 0.1.0: mocked mutation tests do not establish that a real server has
been provisioned successfully. Check the release's validation record before
choosing that path. A running VM does not establish SSH access, successful
cloud-init, or application health.

Keep plans, receipts and inventories in a private working directory outside
the installed module. Do not put secrets in cloud-init data.

## Optional Empire knowledge shelf

The module includes a versioned `legends.knowledge-pack/v1` pack under
`knowledge/hetzner/`. Its suggested home is
`wiki/library/legends-hetzner/hetzner` in your selected Empire.

Installation does not modify a vault. Attachment is a separate preview and
apply operation through [legends-empire](https://github.com/avalonreset/legends-empire):
it creates a user-owned index and versioned reference snapshot. Updates
preserve that index and refuse to overwrite locally edited references.
Private infrastructure decisions and evidence stay in your chosen project.

The current Empire transaction engine supports native Windows attachment
previews; applying requires a supported POSIX environment, such as Linux,
macOS, or correctly configured WSL. This is distinct from the cross-platform
Hetzner runtime. See the module recipe for exact attachment instructions.

## Coolify and MCP

Coolify is optional. This module owns provider-level inspection and provisioning
plans. Coolify owns application deployment and application-level configuration.
Use the companion [legends-coolify](https://github.com/avalonreset/legends-coolify)
for its supported application-platform workflows.

An MCP server is not required. The official CLI is the provider interface;
the knowledge library records the upstream research and boundaries.

## Development and support

- [Agent recipe](docs/AGENT-RECIPE.md)
- [Knowledge index](knowledge/hetzner/vault/index.md)
- [Tested scope](docs/VALIDATION.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Support](SUPPORT.md)
- [Attribution](THIRD_PARTY_NOTICES.md)

Independent software by Benjamin Samar, released under the MIT license.
Not affiliated with or endorsed by Hetzner.
