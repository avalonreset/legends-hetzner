# Disposable live provisioning canary

Use this rehearsal to validate one specific client, provider project and
server configuration. It creates paid resources. Obtain authorization for
one disposable server, one temporary SSH key, a maximum runtime and cleanup
before starting. This is an operator procedure, not an automatic install
step or a broad production-readiness claim.

## Prepare

1. Work in a private temporary directory outside the installed module and
   any published repository. Keep provider tokens in the environment or a
   named `hcloud` context, never in command arguments or files.
2. Record the client OS, Python, module, official `hcloud` and OpenSSH
   versions. Run offline and live `doctor`. Check the selected project's
   current types, locations, images, SSH keys, quota and prices.
3. Generate a temporary Ed25519 key using `ssh-keygen` and register only
   its public half with `hcloud ssh-key create`. Choose a unique canary
   name. Record the returned key ID and fingerprint privately.
4. Prepare secret-free cloud-init data that disables SSH password
   authentication and writes a unique completion marker. Review it before
   passing it to the plan. Never embed the private SSH key or provider token.
5. Select a currently available low-cost type, location and supported
   system image. Record the exact selected values and expected architecture.
   Prepare a cleanup checklist before creating anything.

## Create and verify

With the same explicit authentication selection throughout:

```console
legends-hetzner --context my-project server plan --name CANARY_NAME --type TYPE --location LOCATION --image IMAGE --ssh-key TEMPORARY_KEY_ID --user-data ./canary-cloud-init.yaml --out ./canary-plan.json
legends-hetzner --context my-project server preflight --plan ./canary-plan.json
legends-hetzner --context my-project server create --plan ./canary-plan.json --plan-hash sha256:REVIEWED_HASH --approve --dry-run
legends-hetzner --context my-project server create --plan ./canary-plan.json --plan-hash sha256:REVIEWED_HASH --approve --receipt ./canary-receipt.json
```

Replace every uppercase placeholder. Each line is a separate command on
Windows, macOS or Linux. Keep the receipt even if the command fails.

- Require receipt status `created` and successful readback matching the
  returned server ID, unique name, type, image and location. An
  `uncertain_*` result requires provider inspection; do not retry creation.
- Connect using the temporary key, `BatchMode=yes` and
  `IdentitiesOnly=yes`. Use an isolated `UserKnownHostsFile`. Obtain and
  verify the host fingerprint through an independent trusted channel
  where available. `StrictHostKeyChecking=accept-new` is trust on first
  use, not independent identity verification; record that distinction.
  Never use `StrictHostKeyChecking=no`.
- Wait for cloud-init with a bounded timeout. Require successful
  completion, the exact marker content and effective SSH server
  configuration with password authentication disabled. A `running`
  provider status by itself does not prove these checks.
- Record results privately. Application health, backups, restore and
  unrelated operating systems require their own validation.

## Clean up even after a failed check

The wrapper has no deletion command. Use the official CLI directly after
checking its installed `--help` for exact syntax:

1. Describe the recorded server ID and require its unique canary name and
   identity to match the receipt. Delete only that server by its exact ID.
   If identity is uncertain, inspect before deleting.
2. Delete only the temporary SSH key after checking the recorded ID, name
   and fingerprint. Do not remove pre-existing keys.
3. Inspect primary IP ownership and auto-delete status; remove only a
   canary-owned orphan if one remains. Confirm the canary server, temporary
   key and any canary-owned allocated IPs are absent.
4. Remove the local temporary private key after provider cleanup is
   verified. Keep sanitized version/result evidence and private operational
   receipts as appropriate. Never publish names, addresses, key material,
   account IDs or raw provider inventories.

## Observed canary

On 2026-10-09 the released 0.1.0 wheel passed this lifecycle from Windows
with Python 3.11.7, `hcloud` 1.70.1 and Git for Windows OpenSSH 9.7p1.
The server was CX23 in FSN1 with Ubuntu 24.04. All ten preflight checks
passed; create returned exit 0 and status `created`. Key-based SSH,
cloud-init completion, the marker and disabled SSH password authentication
were verified. Host identity used isolated trust on first use, as described
above. Cleanup verified no canary server, key or allocated IP remained, and
the temporary local private key was removed.

Version 0.1.1 records this evidence without changing the provider execution
path. See `VALIDATION.md` for package, OS and knowledge-attachment coverage.
