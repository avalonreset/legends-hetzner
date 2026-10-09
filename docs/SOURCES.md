# Source ledger

Concise record of the sources behind the v0.1.0 public docs and knowledge
pack. All web sources were observed on 2026-10-09 unless noted. Official
Hetzner sources are authoritative; community sources are labeled as such and
are never the basis for a behavioral guarantee.

## Official Hetzner API and CLI

| # | Source | URL | Observed | Used for |
|---|---|---|---|---|
| 1 | Hetzner Cloud API reference | https://docs.hetzner.cloud/ | 2026-10-09 | API surface and endpoint behavior |
| 2 | Hetzner Cloud API changelog | https://docs.hetzner.cloud/changelog | 2026-10-09 | Recent changes digest in `docs/API-CHANGES.md` |
| 3 | API changelog RSS feed | https://docs.hetzner.cloud/changelog/feed.rss | 2026-10-09 | Cited as the update subscription channel |
| 4 | Official `hcloud` CLI repository | https://github.com/hetznercloud/cli | 2026-10-09 | Provider tool identity, MIT license, manual location |
| 5 | `hcloud` CLI latest release v1.70.1 (published 2026-10-06) | https://github.com/hetznercloud/cli/releases/latest | 2026-10-09 | Current version at research time |
| 6 | Official setup tutorial, dated 2026-09-07 in frontmatter | https://github.com/hetznercloud/cli/blob/main/docs/tutorials/setup-hcloud-cli.md | 2026-10-09 | Install per OS, contexts, first `location list` probe |
| 7 | CLI docs and command manual | https://github.com/hetznercloud/cli/tree/main/docs | 2026-10-09 | Syntax pointer; confirm flags with `--help` |
| 8 | Generating an API token | https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/ | 2026-10-09 | Token creation pointer (linked from source 6) |
| 9 | `hetznercloud` org repositories (33 repos listed, no MCP-named repo among them) | https://api.github.com/orgs/hetznercloud/repos?per_page=100 | 2026-10-09 | Org enumeration behind the MCP finding below |

## Official Hetzner product docs

| # | Source | URL | Observed | Used for |
|---|---|---|---|---|
| 10 | Cloud servers docs hub | https://docs.hetzner.com/cloud/servers/ | 2026-10-09 | Doc locations for create, connect, rescue, console |
| 11 | Servers FAQ | https://docs.hetzner.com/cloud/servers/faq/ | 2026-10-09 | SSH keys, passwords, cloud-init, rebuild access, rescue, mail ports |
| 12 | Enabling backups | https://docs.hetzner.com/cloud/servers/getting-started/enabling-backups/ | 2026-10-09 | Daily automatic backups, 7 slots, oldest deleted when full |
| 13 | Taking snapshots | https://docs.hetzner.com/cloud/servers/getting-started/taking-snapshots/ | 2026-10-09 | Pointer; snapshot timing control per source 11 |
| 14 | Creating a server | https://docs.hetzner.com/cloud/servers/getting-started/creating-a-server/ | 2026-10-09 | Pointer (seen in source 10 navigation) |
| 15 | Connecting to a server | https://docs.hetzner.com/cloud/servers/getting-started/connecting-to-the-server/ | 2026-10-09 | Pointer (seen in source 10 navigation) |
| 16 | Rescue system | https://docs.hetzner.com/cloud/servers/getting-started/rescue-system/ | 2026-10-09 | Pointer (cited by source 11) |
| 17 | VNC console | https://docs.hetzner.com/cloud/servers/getting-started/vnc-console/ | 2026-10-09 | Pointer (seen in source 10 navigation) |
| 18 | Hetzner Cloud Apps docs | https://docs.hetzner.com/cloud/apps | 2026-10-09 | Pointer (cited by source 19) |

## Official Hetzner community and apps

| # | Source | URL | Observed | Used for |
|---|---|---|---|---|
| 19 | Official Cloud Apps repository | https://github.com/hetznercloud/apps | 2026-10-09 | Apps build model (Packer plus cloud-init), support boundary |
| 20 | Official Coolify app README | https://github.com/hetznercloud/apps/blob/main/apps/hetzner/coolify/README.md | 2026-10-09 | Coolify image contents, install, activation, licenses |
| 21 | Basic cloud-config tutorial | https://community.hetzner.com/tutorials/basic-cloud-config/ | 2026-10-09 | cloud-config examples pointer |
| 22 | SSH key how-to (step 4, manual key add) | https://community.hetzner.com/tutorials/howto-ssh-key | 2026-10-09 | Pointer (cited by source 11) |

## Official Hetzner libraries

| # | Source | URL | Observed | Used for |
|---|---|---|---|---|
| 23 | Official Python library | https://github.com/hetznercloud/hcloud-python | 2026-10-09 | Pointer for programmatic use |
| 24 | Official Go library | https://github.com/hetznercloud/hcloud-go | 2026-10-09 | Pointer for programmatic use |
| 25 | Official Terraform provider | https://github.com/hetznercloud/terraform-provider-hcloud | 2026-10-09 | Pointer for infrastructure-as-code use |

## Upstream cloud-init

| # | Source | URL | Observed | Used for |
|---|---|---|---|---|
| 26 | cloud-init examples | https://cloudinit.readthedocs.io/en/latest/topics/examples.html | 2026-10-09 | User-data examples (linked from source 11) |
| 27 | Ubuntu CloudInit help | https://help.ubuntu.com/community/CloudInit | 2026-10-09 | User-data examples (linked from source 11) |

## Community MCP evidence (not official, not required)

| # | Source | URL | Observed | Used for |
|---|---|---|---|---|
| 28 | `hcloud-mcp` by Xodus-CO | https://github.com/Xodus-CO/hcloud-mcp | 2026-10-09 | Community MCP example |
| 29 | `mcp-hetzner` by dkruyt | https://github.com/dkruyt/mcp-hetzner | 2026-10-09 | Community MCP example |
| 30 | `the-real-hetzner-mcp` by mguttmann | https://github.com/mguttmann/the-real-hetzner-mcp | 2026-10-09 | Community MCP example |
| 31 | `hetzner-mcp` on PyPI | https://pypi.org/project/hetzner-mcp/ | 2026-10-09 | Community MCP example |

Finding: no official MCP identified in reviewed official sources as of
2026-10-09. The evidence is the org enumeration in source 9 (33 public
repositories listed, none MCP-named) plus a web search that surfaced only
community projects (sources 28-31). This is an inference from reviewed
sources, not an exhaustive proof of absence: a differently named official
offering or a future release would not be caught by this check. The module
does not need, bundle, or endorse any MCP server either way.

## Module and Empire contracts

| # | Source | Location | Observed | Used for |
|---|---|---|---|---|
| 32 | `docs/CLI-CONTRACT.json` contract v4 | In-repo `docs/` | 2026-10-09 | Exact wrapper syntax, auth rule, exit codes |
| 33 | Module knowledge contract | https://github.com/avalonreset/cto-legends/blob/main/docs/MODULE-KNOWLEDGE.md | 2026-10-09 | Pack shape and ownership model |
| 34 | Empire knowledge-packs doc (`legends-empire`) | https://github.com/avalonreset/legends-empire/blob/main/docs/knowledge-packs.md | 2026-10-09 | Attach and update engine behavior |

## Console and account pointers

- Console: https://console.hetzner.com/ (also reachable as
  https://console.hetzner.cloud/; both hostnames appear in official READMEs).
- Mail addresses: https://accounts.hetzner.com/account/mail (cited by
  source 11 for root-credential delivery).
- Support: https://console.hetzner.com/support (cited by source 6).
- Limit requests (mail ports): https://console.hetzner.com/limits (cited by
  source 11).

## Ledger maintenance

When a runbook gains a new behavioral claim, add the official source row
here first, then cite it. Refresh the changelog digest before each release;
do not reuse this ledger to assert current API behavior after its date.
