# SPDX-License-Identifier: MIT
"""legends-hetzner portable runtime (v0.1.2).

MIT licensed sources. The Hetzner `hcloud` CLI is an external upstream
dependency (not vendored); this package shells to it via argv only.
Live server creation has a validated disposable Windows-client canary:
create/readback, SSH, cloud-init and cleanup. See docs/VALIDATION.md for scope.
"""

__version__ = "0.1.2"
PROVISION_SUPPORT = "live-canary-validated: Windows client, Ubuntu 24.04 server; see docs/VALIDATION.md"
TOOL = "legends-hetzner"

__all__ = ["__version__", "PROVISION_SUPPORT", "TOOL"]
