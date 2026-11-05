# Fractional CTO sizing and rate-limit-safe sniping

Wrapper syntax source of truth is `docs/CLI-CONTRACT.json` (contract v4) in the
installed module. This reference summarizes the Fractional CTO hardware
selection doctrine and the rate-limit-safe stock-sniping workflow.

## 1. Cost-Optimized (`CX` / `CAX`) vs. Regular (`CPX`) and General Purpose (`CCX`)

Hetzner Cloud categorizes server types into three lines (`category`):

- **`cost_optimized` (`CX23`-`CX53` x86 and `CAX11`-`CAX41` ARM64):**
  Primary high-leverage target. Offered **only** in the three European
  `eu-central` locations:
  - **Falkenstein, Germany (`fsn1`)**
  - **Nuremberg, Germany (`nbg1`)**
  - **Helsinki, Finland (`hel1`)**
- **`regular_purpose` (`CPX` shared vCPU):**
  Available in all regions (including US `ash`/`hil` and Singapore `sin`),
  but costs more than 2x per GB of RAM compared to equivalent `CX` tiers.
  Treat `CPX` in Europe only as a temporary bridge when `CX` stock is sold out.
- **`general_purpose` (`CCX` dedicated vCPU):**
  Dedicated threads for sustained heavy CPU loads at a much higher price point.

## 2. Architecture: x86 (`CX23`-`CX53`) vs. ARM64 (`CAX11`-`CAX41`)

### Prefer `x86` (`CX`) by default

1. **Lower cost at every step:** In the current lineup, `CX` x86 tiers cost
   less per month than the corresponding `CAX` ARM64 tiers (`cx23` < `cax11`,
   `cx33` < `cax21`, `cx43` < `cax31`, `cx53` < `cax41`). Check current project
   prices live with `legends-hetzner radar`.
2. **100% `linux/amd64` compatibility:** Every Docker image, headless browser
   (Playwright/Chromium), and prebuilt binary works out of the box without
   emulation.
3. **In-place rescale path:** Hetzner only permits in-place rescaling within
   the same CPU architecture (`x86` <-> `x86` or `arm` <-> `arm`). Starting on
   `cx23` preserves a direct in-place upgrade path to `cx33`, `cx43`, and `cx53`.

### When `ARM64` (`CAX`) is useful

- `CAX` uses Ampere Altra physical ARM64 threads. When all `CX` x86 tiers are
  `available=false` and your workload is 100% `linux/arm64`-compatible, an open
  `cax11` or `cax21` seat is a much cheaper foothold than a `cpx22` fallback.
  Moving later from `CAX` to `CX` requires creating a new `CX` server rather
  than rescaling in place.

## 3. The Fractional CTO tier ladder

| Priority | Tier | Arch | Specs | Role |
| --- | --- | --- | --- | --- |
| **1 (Ideal default)** | **CX43** | `x86` | 8 vCPU · 16 GB · 160 GB NVMe | Best balance of cost and 16 GB RAM headroom for a consolidated stack (Coolify, reverse proxy, websites, databases, and automation workers). |
| **2 (Budget sweet spot)** | **CX33** | `x86` | 4 vCPU · 8 GB · 80 GB NVMe | 2x the CPU and RAM of a `cpx22` fallback at less than half the monthly cost; matches the 80 GB disk of `cpx22` for in-place rescaling. |
| **3 (Starter seat)** | **CX23** | `x86` | 2 vCPU · 4 GB · 40 GB NVMe | Entry seat for Coolify + a lightweight or static/Astro staging site while waiting to rescale up to `cx33` or `cx43`. |
| **4 (Scale-up ceiling)** | **CX53** | `x86` | 16 vCPU · 32 GB · 320 GB NVMe | Heavy single-box consolidation tier before dedicated `CCX` instances are needed. |

### 4 GB starter seat rule (`CX23` / `CAX11`)

When running Coolify + container builds on a 4 GB RAM starter seat, configure a
**4 GB swapfile** on NVMe and cap Node build memory
(`NODE_OPTIONS=--max-old-space-size=2048`) so temporary `astro build` /
`npm build` spikes do not trigger the Linux OOM killer.

### Single-box consolidation rule

Prefer one well-sized `cx43` (16 GB) or `cx53` (32 GB) over multiple small
Hetzner servers. Consolidating onto a single box eliminates duplicate OS/Docker
memory overhead and centralizes firewalling and backups. Audit active servers
with `legends-hetzner inventory`.

## 4. In-place rescale rules

1. **Same location required:** `fsn1` -> `fsn1`, `nbg1` -> `nbg1`, `hel1` -> `hel1`.
   Cross-location moves require snapshot + new server creation.
2. **Same architecture required:** `x86` (`CX`/`CPX`/`CCX`) <-> `x86` only;
   `arm` (`CAX`) <-> `arm` only.
3. **Disk size cannot shrink on full rescale:** Target disk must be `>=` current
   disk (for example an 80 GB `cpx22` can rescale in place to an 80 GB `cx33` or
   160 GB `cx43` in the same location, but not down to a 40 GB `cx23` unless the
   disk was kept at 40 GB via CPU/RAM-only rescaling).

## 5. Rate-limit-safe stock radar and sniping

Scarce `cost_optimized` seats can open for brief windows and be claimed quickly.

### Catalog `available=false` indicators vs. live API placement

Hetzner has two separate capacity layers:

1. **Catalog indicator (`GET /v1/server_types` -> `locations[].available`):**
   Powers the Web Console UI's unavailable badge. It is a cached, conservative
   indicator that can remain `false` when physical host slots are available.
2. **Live placement engine (`POST /v1/servers` via `hcloud server create` and `change_type`):**
   Queries the real-time hypervisor scheduler directly and can allocate a
   `cx43` or `cx33` via the API while the catalog still reports
   `available=false`.

Use the **two-layer strategy** (also emitted in `radar` JSON under
`cto_strategy`):

- **Layer 1 (Direct API Placement via `--allow-unavailable`):** Pass
  `--allow-unavailable` to `server create` or `server snipe` to verify all 9
  non-capacity safety checks and attempt one live `hcloud server create` call
  despite `available=false` in the catalog.
- **Layer 2 (Rate-Limit-Safe Watch):** Never hammer the Hetzner API:
  `legends-hetzner` enforces a minimum `--interval` of `30` seconds (default
  `60`s), random positive `--jitter` (`0..60`s, default `10`s), and bounded
  `--max-polls` (`1..120`, default `30`).

### Sweep or watch stock read-only (`radar`)

```console
legends-hetzner --context my-project radar
legends-hetzner --context my-project radar --germany-only --arch x86 --types cx43,cx33,cx23
legends-hetzner --context my-project radar --germany-only --arch x86 --types cx43,cx33 --watch --interval 60 --jitter 10 --max-polls 30
```

### Snipe a reviewed plan (`server snipe`)

```console
legends-hetzner --context my-project server plan --name app-prod-fsn1 --type cx43 --location fsn1 --image ubuntu-24.04 --ssh-key my-key --out ./plan-cx43-fsn1.json
legends-hetzner --context my-project server snipe --plan ./plan-cx43-fsn1.json --plan-hash sha256:REVIEWED_HASH --approve --dry-run --interval 60 --jitter 10 --max-polls 5
legends-hetzner --context my-project server snipe --plan ./plan-cx43-fsn1.json --plan-hash sha256:REVIEWED_HASH --approve --interval 60 --jitter 10 --max-polls 30 --receipt ./receipt-cx43-fsn1.json
```

`server snipe` aborts immediately on poll 1 if any non-capacity check fails,
makes zero writes while `location_available` is `false`, requires confirmed
`available=true`, and executes at most one `hcloud server create` call when a
seat opens.
