# Optional Coolify boundary

Coolify on Hetzner Cloud is an optional application layer. This module can
provision the server under it; it never manages the inside of Coolify.

## What the Hetzner Coolify app is

- Hetzner maintains a ready-to-deploy Coolify app image (official apps
  repository, ledger source 19; app README, ledger source 20). It was
  announced in the API changelog on 2024-11-05.
- Image contents per the app README: Ubuntu 24.04 with Docker and Coolify
  as containers. Listed licenses in the image: Docker and Coolify (AGPLv3).
- Install by choosing the app instead of a plain OS at server creation, in
  the Console, the API, or `hcloud` with `--image coolify`. The app README
  gives this official example:

  ```bash
  hcloud server create --name my-coolify-server --type cpx11 --image coolify
  ```

- Coolify is preinstalled but not activated until the first server login.
  Log in with the SSH key or the mailed root password, and the activation
  prints the administration interface URL.
- App docs live at `https://docs.hetzner.com/cloud/apps` (ledger source 18).

## Ownership boundary

| Layer | Owner | Notes |
|---|---|---|
| App image build and publish | Hetzner | Packer plus cloud-init build; see the apps repo. Image issues go to Hetzner support. |
| Server lifecycle (create, preflight, keys, backups) | This module plus Hetzner | Planned creates, read-only checks, private server records. |
| Coolify behavior, projects, env vars, domains, in-app backups | Coolify upstream and the server owner | Docs at `https://coolify.io/docs/`. Never in module scope. |
| Credentials and app data on the server | Server owner | Keep in the owner records, never in this repo or pack. |

The module bundles no Coolify software (see `THIRD_PARTY_NOTICES.md`).
Nothing in the wrapper reads or writes Coolify state.

## Suggested practice

1. Preflight the server exactly like any other planned server: image name
   `coolify`, a type with enough headroom for containers, keys registered.
2. Record the app choice, activation URL, and admin owner in the private
   server record, not in the plan file.
3. Keep Coolify upgrades, project config, and domain wiring in Coolify
   itself plus owner notes. A server rebuild from snapshot follows the
   normal rebuild access rules in `docs/SSH-BOOTSTRAP.md`.
4. Route problems: deployment or image faults to Hetzner support, Coolify
   behavior to Coolify docs and community, wrapper faults to the module
   issue tracker with a redacted receipt.
