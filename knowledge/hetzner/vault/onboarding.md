# Onboarding

Source: official setup tutorial
`https://github.com/hetznercloud/cli/blob/main/docs/tutorials/setup-hcloud-cli.md`
(dated 2026-09-07), observed 2026-10-09. The tutorial wins on drift.

## Install `hcloud`

Research-time latest was v1.70.1 (published 2026-10-06). QA for module
v0.1.0 should use v1.70.1 unless the releases page shows newer. Manual
installs do not auto-update.

- Windows: `winget install HetznerCloud.CLI` or `scoop install hcloud`
  (not maintained by Hetzner per the tutorial).
- macOS: `brew install hcloud`.
- Debian/Ubuntu `.deb`, Fedora/RHEL `.rpm`: experimental per tutorial.
- Pinned manual binary with checksum verification (Linux 64-bit shown):

  ```bash
  HCLOUD_VERSION=1.70.1
  curl -sSLO "https://github.com/hetznercloud/cli/releases/download/v${HCLOUD_VERSION}/hcloud-linux-amd64.tar.gz"
  curl -sSLO "https://github.com/hetznercloud/cli/releases/download/v${HCLOUD_VERSION}/checksums.txt"
  grep hcloud-linux-amd64.tar.gz checksums.txt | sha256sum -c -
  sudo tar -C /usr/local/bin --no-same-owner -xzf hcloud-linux-amd64.tar.gz hcloud
  ```

- Docker is an upstream alternative only:
  `docker run --rm -e HCLOUD_TOKEN hetznercloud/cli:latest <command>`
  (inherit the token from the host environment, never a literal token).
  The wrapper expects a local `hcloud` executable; there is no native
  Docker adapter.

Verify: `hcloud version`.

## Install the module

```bash
cto-legends install legends-hetzner
cto-legends install legends-hetzner --apply
```

From source: Python 3.10+ only, then `python -m legends_hetzner --version`
(`python3` where Python is named that; the `legends-hetzner` console
script takes the same arguments).

## Token, context, first probes

Create one API token per project in the Console
(`https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/`),
then:

```bash
hcloud context create <context-name>
python -m legends_hetzner doctor
python -m legends_hetzner --context <context-name> doctor --live
python -m legends_hetzner --context <context-name> catalog --kind locations
```

All wrapper output is JSON to stdout. Offline `doctor` exits nonzero
when `hcloud` is missing or errored.

## Record

OS and arch, `hcloud version`, wrapper `--version`, context name (never
the token), commands, exit codes. Keep per-OS evidence separate.
