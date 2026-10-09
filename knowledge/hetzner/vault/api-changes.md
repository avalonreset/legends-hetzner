# API changes (module-relevant)

Digest of `https://docs.hetzner.cloud/changelog`, observed 2026-10-09.
All anchors below were copied from that page. Scoped to servers, images,
types, locations, keys, user data, and catalog shapes. Omitted on purpose:
load balancers, DNS, networks, firewalls, volumes, storage, certificates.

## Must-handle

- 2026-10-01: Data Center endpoints return 410 Gone.
  `https://docs.hetzner.cloud/changelog#2026-10-01-datacenters-removed`
- 2026-09-08: `deprecated` field removed 2026-11-02; read `deprecation`.
  `https://docs.hetzner.cloud/changelog#2026-09-08-removing-the-deprecated-field`
- 2026-07-01: Datacenter properties removed for Primary IPs and Servers.
  `https://docs.hetzner.cloud/changelog#2026-07-01-removing-datacenters`
- 2026-04-30: `GET /<resource>/{id}/actions/{action_id}` deprecated.
  `https://docs.hetzner.cloud/changelog#2026-04-30-deprecate-get-resource-action-endpoints`
- 2026-04-22: Leading whitespace in SSH keys invalid.
  `https://docs.hetzner.cloud/changelog#2026-04-22-ssh-key-validation`
- 2026-04-01: Datacenter server_types info and recommendation fields
  deprecated.
  `https://docs.hetzner.cloud/changelog#2026-04-01-datacenter-deprecations`
- 2025-12-16: Phasing out Datacenters in favor of Locations.
  `https://docs.hetzner.cloud/changelog#2025-12-16-phasing-out-datacenters`
- 2025-09-24: Per Location Server Types; check type-in-location.
  `https://docs.hetzner.cloud/changelog#2025-09-24-per-location-server-types`

## Boot and metadata

- 2026-06-30: EC2-compatible metadata routes deprecated; names
  `/hetzner/v1/*` as officially documented.
  `https://docs.hetzner.cloud/changelog#2026-06-30-deprecated-metadata-routes`
- 2026-08-01: EC2-compatible metadata routes removed.
  `https://docs.hetzner.cloud/changelog#2026-08-01-removed-metadata-routes`
- 2026-05-18: Private network auto-configuration via cloud-init.
  `https://docs.hetzner.cloud/changelog#2026-05-18-private-network-auto-configuration-via-cloud-init`
- 2026-01-16: `user_data` available for rebuilds.
  `https://docs.hetzner.cloud/changelog#2026-01-16-server-rebuild-with-user-data`

## Types and images

- 2025-10-16: New Server Types / old shared-vCPU deprecated.
  `https://docs.hetzner.cloud/changelog#2025-10-16-new-server-types-with-categories`
  `https://docs.hetzner.cloud/changelog#2025-10-16-server-types-deprecated`
- 2025-08-25: Category for Server Types.
  `https://docs.hetzner.cloud/changelog#2025-08-25-category-for-server-types`
- Images available: Fedora 44, Ubuntu 26.04 (2026-05-18:
  `https://docs.hetzner.cloud/changelog#2026-05-18-fedora-44-and-ubuntu-2604-now-available`),
  Fedora 43, openSUSE Leap 16 (2025-12-18:
  `https://docs.hetzner.cloud/changelog#2025-12-18-fedora-43-and-opensuse-16-now-available`).
- Images deprecated or unavailable: Debian 11 (deprecated 2026-08-31,
  unavailable after 2026-11-30:
  `https://docs.hetzner.cloud/changelog#2026-08-31-debian-11-image-is-deprecated`),
  openSUSE 15 (unavailable 2026-07-30:
  `https://docs.hetzner.cloud/changelog#2026-07-30-opensuse-15-image-is-unavailable-for-new-orders`),
  Fedora 42 (unavailable 2026-06-30:
  `https://docs.hetzner.cloud/changelog#2026-06-30-fedora-42-image-is-unavailable-for-new-orders`),
  Fedora 41 (unavailable 2026-02-05:
  `https://docs.hetzner.cloud/changelog#2026-02-05-fedora-41-image-is-unavailable-for-new-orders`),
  Ubuntu 20.04 (unavailable 2025-08-01:
  `https://docs.hetzner.cloud/changelog#2025-08-01-ubuntu-2004-is-unavailable-for-new-orders`).

## App boundary

- 2024-11-05 entry "New App: Coolify.io" on
  `https://docs.hetzner.cloud/changelog` (find by date and title; no deep
  anchor shipped).

Preflight checks the live catalog; this digest is a pointer.
