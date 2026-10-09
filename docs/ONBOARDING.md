# Onboarding: Windows, macOS, Linux

Goal: the official `hcloud` CLI installed, the wrapper importable, and a
first read-only probe green. Install steps below follow the official setup
tutorial (ledger source 6, dated 2026-09-07); the tutorial is authoritative
if this page drifts.

## 1. Install `hcloud`

Latest release at research time was v1.70.1, published 2026-10-06 (ledger
source 5). QA and remote verification for this module version should use
v1.70.1 unless the releases page shows a newer version; record the exact
version verified. Manual installs do not auto-update. The tutorial warns
that some third-party package repositories ship outdated versions.

Prefer a platform installer when one fits:

- Windows: `winget install HetznerCloud.CLI` or `scoop install hcloud`.
  The tutorial warns these entries are not maintained by Hetzner; prefer
  the GitHub release binary if a package misbehaves.
- macOS: `brew install hcloud`.
- Debian/Ubuntu (`.deb`) and Fedora/RHEL (`.rpm`): both package formats
  are experimental per the tutorial and may change or break. Download the
  pinned version from the releases page and install with `dpkg -i` or
  `dnf`/`rpm -i`.

Otherwise use a pinned manual binary with checksum verification (Linux
64-bit shown; pick the matching asset for your OS and arch from the
release):

```bash
HCLOUD_VERSION=1.70.1
curl -sSLO "https://github.com/hetznercloud/cli/releases/download/v${HCLOUD_VERSION}/hcloud-linux-amd64.tar.gz"
curl -sSLO "https://github.com/hetznercloud/cli/releases/download/v${HCLOUD_VERSION}/checksums.txt"
grep hcloud-linux-amd64.tar.gz checksums.txt | sha256sum -c -
sudo tar -C /usr/local/bin --no-same-owner -xzf hcloud-linux-amd64.tar.gz hcloud
rm hcloud-linux-amd64.tar.gz checksums.txt
```

The `checksums.txt` asset and the `releases/download/v<VERSION>/` URL shape
were verified against the v1.70.1 release metadata (ledger source 5). Do
not install a binary whose checksum fails.

Two further upstream options from the tutorial, with caveats:

- Go toolchain: `go install github.com/hetznercloud/cli/cmd/hcloud@latest`.
  Binaries built this way do not have the correct version embedded.
- Docker (upstream alternative, no host install). Inherit the token from
  the host environment; never place a literal token in the command:

  ```bash
  docker run --rm -e HCLOUD_TOKEN hetznercloud/cli:latest <command>
  ```

  The wrapper expects a local `hcloud` executable (see `--hcloud-bin`).
  There is no native Docker adapter: running `hcloud` in Docker does not
  wire it into the wrapper.

Verify the install:

```bash
hcloud version
```

Optional: enable shell completion for bash, zsh, fish, or PowerShell as
described in the tutorial.

## 2. Install the module

Preferred route is the router preview, then an explicit apply when that
install is within the authorized task:

```bash
cto-legends install legends-hetzner
cto-legends install legends-hetzner --apply
```

From a source checkout, the wrapper needs Python 3.10+ and nothing else
(standard library only):

```bash
python -m legends_hetzner --version
```

On systems where Python is named `python3` (typical macOS and Linux), use
`python3 -m legends_hetzner` instead. All `python -m` examples in these
docs mean "the Python 3.10+ interpreter on PATH", and the installed
`legends-hetzner` console script takes the same arguments.

## 3. Token and context

Create one API token per Hetzner Cloud project in the Console (see
`docs/AUTH.md` and the official token doc, ledger source 8), then create a
named context:

```bash
hcloud context create <context-name>
```

Keep the context name similar to the project name. The wrapper accepts
either this context (via `--context NAME`) or a `HCLOUD_TOKEN` environment
variable, never both in one invocation.

## 4. First probes

Offline check, no auth and no network writes:

```bash
python -m legends_hetzner doctor
```

Live read-only checks (explicit auth required). Global flags come before
the subcommand, matching the README and the contract:

```bash
python -m legends_hetzner --context <context-name> doctor --live
python -m legends_hetzner --context <context-name> catalog --kind locations
```

The installed `legends-hetzner` console script takes the same arguments:

```bash
legends-hetzner --context <context-name> doctor --live
```

Expected locations include `fsn1`, `nbg1`, `hel1`, `ash`, `hil`, and `sin`
at tutorial time; treat the live output as current. All wrapper output is
JSON to stdout. Exit 0 means the probe passed.

Direct `hcloud` equivalent from the tutorial:

```bash
hcloud location list
```

## 5. Evidence to record

For each onboarding, record: OS and architecture, `hcloud version` output,
wrapper `--version` output, context name (never the token), each command run,
each exit code, and a note that output was redacted. Keep per-OS evidence
separate. Onboarding steps above were researched from official docs on
2026-10-09. Measured platform evidence is in `docs/VALIDATION.md`,
including the Windows live read-only pass with real `hcloud` 1.61.0.
