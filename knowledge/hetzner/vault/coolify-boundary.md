# Coolify boundary (optional)

The module provisions the server under Coolify; it never manages inside
Coolify.

## The Hetzner Coolify app

- Official Hetzner-maintained image
  (`https://github.com/hetznercloud/apps/blob/main/apps/hetzner/coolify/README.md`,
  observed 2026-10-09; announced 2024-11-05). Ubuntu 24.04 with Docker and
  Coolify containers. Listed licenses: Docker, Coolify AGPLv3.
- Install by choosing the app at creation:
  `hcloud server create --name my-coolify-server --type cpx11 --image coolify`
  (official example from the app README).
- Preinstalled but inactive until first login, which prints the admin URL.
- App docs: `https://docs.hetzner.com/cloud/apps`.

## Boundary

- Image build and publish: Hetzner. Image faults go to Hetzner support.
- Server lifecycle: this module plus Hetzner.
- Coolify behavior, projects, env vars, domains, in-app backups: Coolify
  upstream (`https://coolify.io/docs/`) and the server owner. Never module
  scope. The companion `legends-coolify` covers application-platform
  workflows.
- Credentials and app data: server owner, in owner records only.

The module bundles no Coolify software. Record the app choice, activation
URL, and admin owner in the private server record.
