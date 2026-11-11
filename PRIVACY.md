# Privacy Policy

`legends-hetzner` is an open-source, local-first CLI and knowledge pack for Hetzner Cloud operations.

## Data Collection & Telemetry

- **Zero Telemetry:** This package collects no analytics, usage telemetry, crash reports, or device identifiers.
- **No Third-Party Phone-Home:** The CLI only communicates with the local `hcloud` binary and `https://api.hetzner.cloud/v1/server_types` when explicitly invoked for live operations.
- **Local Execution:** Offline commands (`doctor`, `resources`, `server plan`, `check_release.py`) execute strictly locally without network traffic.

## Credentials & Local State

- Credentials are supplied via the `HCLOUD_TOKEN` environment variable or managed by the official `hcloud` CLI via `--context`.
- Raw secret values are redacted from JSON output and error messages before emission.
- Plan and receipt artifacts are written only to explicit user-specified `--out` or `--receipt` file paths.
