# Validation for 0.1.0

Observed 2026-10-09. These results describe tested behavior, not a guarantee
for every provider account, OS release or future API response.

## Platform and package checks

The 148-test suite passed on native Windows. Hosted CI passed all six
Windows, macOS and Ubuntu jobs on Python 3.10 and 3.14, including the
release scan, tests, wheel/source builds, wheel installation outside the
checkout, resource discovery and all 15 knowledge-file hashes.
See the [verified matrix run](https://github.com/avalonreset/legends-hetzner/actions/runs/37949067541).

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

Live server creation, paid resource cleanup, SSH to a newly provisioned
server, cloud-init completion and application health have **not** been
validated. Creation remains experimental. Mocked provider tests exercise
guards and uncertainty handling but cannot establish a working live
provisioning lifecycle.

## Knowledge integration

The shipped knowledge pack was exercised against `legends-empire` 0.3.0
using its actual knowledge and transaction engines in a disposable POSIX
vault under WSL. The check passed:

- Preview made no vault changes.
- Fresh attachment created the reference snapshot.
- Repeating the same attachment produced no writes.
- A synthetic upstream update preserved the user index and private notes.
- A locally edited reference blocked attachment before mutation.

The reproducible check is `scripts/verify_knowledge_attachment.py`. It
requires an explicit Empire source path and creates only a temporary
synthetic vault. Native Windows attachment apply remains unsupported by
the current Empire engine; preview is supported.

## Evidence boundaries

No cloud resources were purchased or changed for this validation. The
package does not bundle Hetzner credentials, SSH private keys, private
inventories, account identifiers, local fleet addresses or personal vault
paths. Public examples use placeholders.

The official provider CLI is separately installed. An offline doctor
failure when it is absent is expected setup guidance, not proof of a
package installation failure.
