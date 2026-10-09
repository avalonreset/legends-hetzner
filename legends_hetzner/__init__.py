# SPDX-License-Identifier: MIT
"""legends-hetzner portable runtime (v0.1.0).

MIT licensed sources. The Hetzner `hcloud` CLI is an external upstream
dependency (not vendored); this package shells to it via argv only.
Provision support in v0.1.0 is mocked-write-only until an explicit
disposable resource test validates live server create.
"""

__version__ = "0.1.0"
PROVISION_SUPPORT = "mocked-write-only until explicit disposable resource test"
TOOL = "legends-hetzner"

__all__ = ["__version__", "PROVISION_SUPPORT", "TOOL"]
