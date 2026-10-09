# Validation for 0.1.1

Observed 2026-10-09. These results describe tested behavior, not a guarantee
for every provider account, OS release or future API response.

## Platform and package checks

For the initial 0.1.0 release, the 148-test suite passed on native Windows.
Hosted CI passed all six Windows, macOS and Ubuntu jobs on Python 3.10 and
3.14, including the
release scan, tests, wheel/source builds, wheel installation outside the
checkout, resource discovery and all 15 knowledge-file hashes.
See the [verified matrix run](https://github.com/avalonreset/legends-hetzner/actions/runs/37949396480).

For the 0.1.1 candidate, all 148 tests and the public release scan passed
again on Windows. Final release checks are recorded in the repository's
checks workflow.

Separate native fleet checks exercised an isolated wheel installation:

| Platform | Python | Official CLI | Result |
| --- | --- | --- | --- |
| Windows x64 | 3.11.7 | 1.70.1 | Installed command, offline doctor, packaged resources and pack hashes passed. |
| Debian 13 x64 | 3.13.5 | 1.70.1 | Installed command, offline doctor, offline plan, missing-auth refusal, resources and pack hashes passed. |
| macOS 26.6.2 arm64 | 3.13.7 | 1.70.1 | Installed command, offline doctor, offline plan, missing-auth refusal, resources and pack hashes passed. |

Native platform checks used separately staged official CLI binaries and
isolated Python environments. Provider credentials were not copied to the
macOS or Linux test environments. Their readiness checks were offline;
authenticated provider checks below were performed on Windows.
The macOS system Python 3.9 was deliberately not used because it is below
the package's declared Python 3.10 minimum.

## Provider behavior

Windows with Python 3.11.7 and official `hcloud` 1.61.0 and 1.70.1 passed offline
readiness, authenticated live readiness, inventory and all catalog reads.
Credentials and private inventory were kept outside the public repository.

With `hcloud` 1.70.1, a live read-only preflight and create dry-run passed
all ten checks: name availability, type, location, image, existing SSH-key
ID, type/location support and capacity indicator, deprecation and image
architecture compatibility. The official CLI archive was checked against
the upstream release checksum before use.

An additional disposable live canary on 2026-10-09 used the released 0.1.0
wheel from Windows with Python 3.11.7, `hcloud` 1.70.1 and Git for Windows
OpenSSH 9.7p1. One CX23 server in FSN1 used the Ubuntu 24.04 system image
and secret-free cloud-init data:

- All ten preflight and dry-run checks passed.
- Create returned exit 0 and receipt status `created`; provider readback
  confirmed the planned resource.
- Key-based SSH succeeded. The isolated known-hosts policy was trust on
  first use (`accept-new`), not independent host fingerprint verification.
- cloud-init completed, the exact completion marker was verified, and
  effective SSH configuration disabled password authentication.
- Cleanup verified no canary server, temporary SSH key or allocated IP
  remained. The temporary local private key was removed. Existing
  resources were preserved.

Version 0.1.1 records this evidence without changing the provider execution
path. This canary does not validate live writes from macOS or Linux
clients, every type/image/location combination, application health, or
backup restores. Mocked tests separately exercise guards and uncertainty
handling. See `docs/LIVE-CANARY.md` for the reproducible operator procedure.

## Knowledge integration

The 0.1.0 knowledge pack passed integration with `legends-empire` 0.3.0
in a disposable POSIX vault under WSL. The 0.1.1 pack then passed against
the Empire 0.3.1 candidate on **native Windows**, Python 3.11.7, using a
temporary local NTFS vault and the actual knowledge and transaction engines.
Both checks passed all five scenarios:

- Preview made no vault changes.
- Fresh attachment created the reference snapshot.
- Repeating the same attachment produced no writes.
- A synthetic upstream update preserved the user index and private notes.
- A locally edited reference blocked attachment before mutation.

The reproducible check is `scripts/verify_knowledge_attachment.py`. It
requires an explicit Empire source path and creates only a temporary
synthetic vault. Native Windows requires Empire 0.3.1+; the old unconditional
Windows refusal was replaced with an engine-version readiness check.

A separate CI job runs this integration from an installed Hetzner wheel
on Windows, macOS and Linux with Python 3.11 against an immutable Empire
commit. The core wrapper still supports Python 3.10+. Native Windows
filesystem and durability limits are described in `docs/KNOWLEDGE-PACK.md`;
this acceptance check does not claim power-loss recovery.

## Evidence boundaries

Only the explicitly authorized disposable canary resources were created
and removed for the live lifecycle check. The package does not bundle
Hetzner credentials, SSH private keys, private inventories, account
identifiers, local fleet addresses or personal vault
paths. Public examples use placeholders.

The official provider CLI is separately installed. An offline doctor
failure when it is absent is expected setup guidance, not proof of a
package installation failure.
