# Validation for 0.1.0

Observed 2026-10-09. These results describe tested behavior, not a guarantee
for every provider account, OS release or future API response.

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
