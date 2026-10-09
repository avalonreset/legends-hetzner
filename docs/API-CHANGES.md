# Recent official API changes

Focused digest for this module's scope: servers, images, server types,
locations, SSH keys, user data, and catalog shapes. Source is the Hetzner
Cloud API changelog (`https://docs.hetzner.cloud/changelog`), observed
2026-10-09. Every link below is an anchor copied from that page. Refresh
this digest before each release. Subscribe to
`https://docs.hetzner.cloud/changelog/feed.rss` for updates.

Out of scope here on purpose: load balancers, DNS, networks, firewalls,
volumes, storage, certificates, and object storage have no wrapper commands
in v0.1.1, so their changelog entries are omitted. Read the full changelog
before touching those resources.

## Must-handle changes

| Date | Entry | Why it matters here |
|---|---|---|
| 2026-10-01 | [Data Center endpoints return HTTP 410 Gone](https://docs.hetzner.cloud/changelog#2026-10-01-datacenters-removed) | Datacenter endpoints are removed. Plan and preflight use locations only. |
| 2026-09-08 | [Field `deprecated` will be removed](https://docs.hetzner.cloud/changelog#2026-09-08-removing-the-deprecated-field) | Removal date 2026-11-02. Catalog parsing must read `deprecation` on Images and Server Types (per location), not `deprecated`. |
| 2026-07-01 | [Remove Datacenters properties for Primary IPs and Servers](https://docs.hetzner.cloud/changelog#2026-07-01-removing-datacenters) | Server objects no longer carry datacenter properties. |
| 2026-06-02 | [Deprecation Data Center endpoints](https://docs.hetzner.cloud/changelog#2026-06-02-datacenters-deprecated) | Announcement behind the 2026-10-01 removal. |
| 2026-04-30 | [All GET /\<resource>/{id}/actions/{action_id} operations are deprecated](https://docs.hetzner.cloud/changelog#2026-04-30-deprecate-get-resource-action-endpoints) | If readback polls single actions this way, it needs a migration path. |
| 2026-04-22 | [Leading whitespace characters in SSH Keys are invalid](https://docs.hetzner.cloud/changelog#2026-04-22-ssh-key-validation) | Trim key material before registering keys. |
| 2026-04-01 | [Datacenter server_types information and recommendation fields are deprecated](https://docs.hetzner.cloud/changelog#2026-04-01-datacenter-deprecations) | Do not parse datacenter-nested type info or recommendation fields. |
| 2025-12-16 | [Phasing out Datacenters in favor of Locations for Primary IPs and Servers](https://docs.hetzner.cloud/changelog#2025-12-16-phasing-out-datacenters) | Announcement behind the datacenter removals. Prefer locations everywhere. |
| 2025-09-24 | [Per Location Server Types](https://docs.hetzner.cloud/changelog#2025-09-24-per-location-server-types) | Type availability is per location (`server_types[].locations[]` with availability). Preflight must check type-in-location, not type alone. |

Note: both the per-location availability shape and the `deprecated` to
`deprecation` migration affect catalog parsing. Preflight checks the live
API; this digest only points at the change.

## Server metadata and boot

| Date | Entry | Why it matters here |
|---|---|---|
| 2026-06-30 | [EC2-compatible routes for Server Metadata are deprecated](https://docs.hetzner.cloud/changelog#2026-06-30-deprecated-metadata-routes) | Names `/hetzner/v1/*` as the officially documented routes; EC2 routes removed 2026-08-01. |
| 2026-08-01 | [EC2-compatible routes for Server Metadata were removed](https://docs.hetzner.cloud/changelog#2026-08-01-removed-metadata-routes) | Do not build on EC2-style metadata paths. |
| 2026-05-18 | [Private Networks auto-configuration is available via cloud-init](https://docs.hetzner.cloud/changelog#2026-05-18-private-network-auto-configuration-via-cloud-init) | Relevant to user-data design for private networks. |
| 2026-01-16 | [user_data now available for Server rebuilds](https://docs.hetzner.cloud/changelog#2026-01-16-server-rebuild-with-user-data) | Rebuilds accept user data; see `docs/SSH-BOOTSTRAP.md`. |

## Server types

| Date | Entry | Why it matters here |
|---|---|---|
| 2025-10-16 | [New Server Types](https://docs.hetzner.cloud/changelog#2025-10-16-new-server-types-with-categories) | Current type lineup with categories. |
| 2025-10-16 | [Old Server Types with shared vCPUs are deprecated](https://docs.hetzner.cloud/changelog#2025-10-16-server-types-deprecated) | Avoid old shared-vCPU types in new plans. |
| 2025-08-25 | [Category for Server Types](https://docs.hetzner.cloud/changelog#2025-08-25-category-for-server-types) | Catalog shape carries a category field. |

## Image lifecycle

| Date | Entry | Why it matters here |
|---|---|---|
| 2026-08-31 | [Debian 11 image is deprecated](https://docs.hetzner.cloud/changelog#2026-08-31-debian-11-image-is-deprecated) | Unavailable for new servers after 2026-11-30. |
| 2026-07-30 | [OpenSUSE 15 image is unavailable for new servers](https://docs.hetzner.cloud/changelog#2026-07-30-opensuse-15-image-is-unavailable-for-new-orders) | Do not plan on it. |
| 2026-06-30 | [Fedora 42 image is unavailable for new servers](https://docs.hetzner.cloud/changelog#2026-06-30-fedora-42-image-is-unavailable-for-new-orders) | Do not plan on it. |
| 2026-05-18 | [Fedora 44 and Ubuntu 26.04 are now available](https://docs.hetzner.cloud/changelog#2026-05-18-fedora-44-and-ubuntu-2604-now-available) | Current image options. |
| 2026-04-30 | [OpenSUSE 15 image is deprecated](https://docs.hetzner.cloud/changelog#2026-04-30-opensuse-15-image-is-deprecated) | Announcement behind the 2026-07-30 removal. |
| 2026-03-30 | [Fedora 42 image is deprecated](https://docs.hetzner.cloud/changelog#2026-03-30-fedora-42-image-is-deprecated) | Announcement behind the 2026-06-30 removal. |
| 2026-02-05 | [Fedora 41 image is unavailable for new servers](https://docs.hetzner.cloud/changelog#2026-02-05-fedora-41-image-is-unavailable-for-new-orders) | Do not plan on it. |
| 2025-12-18 | [Fedora 43 and openSUSE Leap 16 now available](https://docs.hetzner.cloud/changelog#2025-12-18-fedora-43-and-opensuse-16-now-available) | Current image options. |
| 2025-10-28 | [Fedora 41 image is deprecated](https://docs.hetzner.cloud/changelog#2025-10-28-fedora-41-image-is-deprecated) | Announcement behind the 2026-02-05 removal. |
| 2025-08-01 | [Ubuntu 20.04 is unavailable for new orders](https://docs.hetzner.cloud/changelog#2025-08-01-ubuntu-2004-is-unavailable-for-new-orders) | Do not plan on it. |

## App boundary

- 2024-11-05, entry "New App: Coolify.io" on the changelog page
  (`https://docs.hetzner.cloud/changelog`). No deep anchor is shipped for
  this row because none was captured during research; find it by date and
  title on the page. See `docs/COOLIFY-BOUNDARY.md`.

Preflight always checks the live catalog; this digest is a pointer, not a
substitute.
