# Fractional CTO sizing and rate-limit-safe sniping

This guide captures the Fractional CTO hardware selection doctrine and the
rate-limit-safe stock-sniping workflow built into `legends-hetzner` v0.1.3.
For exact CLI flags and exit codes, `docs/CLI-CONTRACT.json` is authoritative.

## 1. Why the Cost-Optimized line is the primary target

Hetzner Cloud organizes server types into three categories (`server_types[].category`):

1. **`cost_optimized` (`CX23`–`CX53` x86 and `CAX11`–`CAX41` ARM64):**
   The highest price-to-performance cloud tiers Hetzner offers.
2. **`regular_purpose` (`CPX` shared vCPU):**
   Available across all regions, but typically costs more than 2x per GB of
   RAM compared to equivalent `cost_optimized` tiers. Treat `CPX` in Europe as
   a temporary fallback when `CX` stock is exhausted, not a long-term default.
3. **`general_purpose` (`CCX` dedicated vCPU):**
   Dedicated physical threads for sustained CPU-bound production loads at a
   significantly higher monthly price point.

### The three European Cost-Optimized locations (`eu-central`)

Hetzner offers the `cost_optimized` (`CX` and `CAX`) line **only** in three
European locations:

- **Falkenstein, Germany (`fsn1`)** — Flagship German campus; lowest central
  European latency and highest capacity demand.
- **Nuremberg, Germany (`nbg1`)** — Second German campus; identical German
  jurisdiction and network profile to `fsn1`.
- **Helsinki, Finland (`hel1`)** — Modern Nordic campus; frequently has open
  `cost_optimized` seats when `fsn1` and `nbg1` are temporarily sold out.

US (`ash`, `hil`) and Singapore (`sin`) locations do not carry the
`cost_optimized` category. Unless strict non-European data residency or
sub-30ms US/APAC latency is mandatory, deploying in `fsn1`, `nbg1`, or `hel1`
unlocks the `CX`/`CAX` price-performance curve.

## 2. Architecture choice: x86 (`CX`) vs. ARM64 (`CAX`)

Both `CX` (Intel/AMD `x86`) and `CAX` (Ampere Altra `arm`) belong to the
`cost_optimized` category and share the same vCPU, RAM, and NVMe step sizes
(2/4/8/16 vCPU and 4/8/16/32 GB RAM).

### Why `x86` (`CX23`–`CX53`) is the default recommendation

1. **Lower monthly cost at every tier:** In the current `CX23`–`CX53`
   generation, the `x86` tiers are priced below the `CAX11`–`CAX41` ARM64
   tiers at every single size step. Always inspect live project pricing via
   `legends-hetzner radar`.
2. **Universal `linux/amd64` compatibility:** Every prebuilt Docker image,
   Playwright/Chromium browser binary, database plugin, and third-party CLI
   tool runs natively on `x86` without emulation overhead or missing-arch
   container build failures.
3. **In-place rescale ladder:** Hetzner only allows in-place server rescaling
   within the **same CPU architecture**. Starting on `cx23` preserves a
   direct, zero-migration upgrade path up to `cx33`, `cx43`, and `cx53`.

### When `ARM64` (`CAX11`–`CAX41`) is a smart alternative

- `CAX` cores are non-hyperthreaded Ampere Altra physical ARM64 cores with
  strong steady-state throughput.
- When all `CX` x86 seats are temporarily sold out (`available=false`) and an
  immediate `cost_optimized` foothold is needed for a pure `linux/arm64` stack
  (for example Coolify + Astro/Node/PostgreSQL/Nginx without x86-only binaries),
  an open `cax11` or `cax21` seat is dramatically cheaper than falling back to
  `cpx22`. Keep in mind that switching later from `CAX` (ARM) to `CX` (x86)
  requires provisioning a new `CX` server rather than rescaling in place.

## 3. The Fractional CTO tier ladder (`CX23` -> `CX33` -> `CX43` -> `CX53`)

| Rank | Tier | Arch | Specs (vCPU / RAM / NVMe) | Fractional CTO role |
| --- | --- | --- | --- | --- |
| **1 (Ideal default)** | **CX43** | `x86` | 8 vCPU · 16 GB · 160 GB | **Target default for most teams.** 16 GB RAM comfortably hosts a consolidated stack (Coolify, reverse proxy, websites, databases, and automation workers) without memory pressure during container builds. |
| **2 (Budget sweet spot)** | **CX33** | `x86` | 4 vCPU · 8 GB · 80 GB | **Best lean production value.** Delivers 2x the CPU and RAM of a `cpx22` fallback at less than half the monthly cost, with an 80 GB NVMe disk that accepts an in-place rescale from an 80 GB `cpx22` in the same location. |
| **3 (Starter seat)** | **CX23** | `x86` | 2 vCPU · 4 GB · 40 GB | **Entry foothold.** Sufficient to deploy Coolify and a lightweight or static/Astro staging site while waiting to rescale up to `cx33` or `cx43`. |
| **4 (Scale-up ceiling)** | **CX53** | `x86` | 16 vCPU · 32 GB · 320 GB | **Heavy single-box consolidation ceiling.** Handles large multi-service estates on one box before dedicated `CCX` tiers are ever needed. |

### Operational rule for 4 GB starter seats (`CX23` and `CAX11`)

A 4 GB server running Docker + Coolify idles around 1.2–1.5 GB RAM, leaving
roughly 2.5 GB for container builds. When building Node, Astro, or Next.js
projects on a 4 GB seat:

1. **Always configure a 4 GB swapfile** (`fallocate -l 4G /swapfile`,
   `chmod 600 /swapfile`, `mkswap /swapfile`, `swapon /swapfile`, and persist
   in `/etc/fstab`) so brief `npm build` / `astro build` memory spikes page to
   NVMe swap instead of triggering the Linux OOM killer.
2. **Bound Node build memory** (for example `NODE_OPTIONS=--max-old-space-size=2048`)
   until the server is rescaled to `cx33` (8 GB) or `cx43` (16 GB).

### Single-box consolidation vs. multiple small servers

Avoid inadvertently running multiple small Hetzner servers when a single
`cx43` (16 GB) or `cx53` (32 GB) can consolidate those workloads:

- Every extra VPS wastes 1–1.5 GB of RAM on duplicate kernel, systemd, Docker,
  and Coolify/agent overhead.
- A single consolidated `cx43` or `cx53` gives every hosted service access to
  shared burst CPU and RAM headroom, one firewall policy, and one backup/snapshot
  schedule.
- Use `legends-hetzner inventory` to audit active servers and confirm no
  forgotten fallback or duplicate instances remain running.

## 4. In-place rescale rules and pitfalls

Hetzner Cloud supports upgrading a server's tier in place (brief power-off cycle,
preserving the server ID, IPv4/IPv6 addresses, and disk data) only when three
provider rules are satisfied:

1. **Same location (`fsn1` -> `fsn1`, `nbg1` -> `nbg1`, `hel1` -> `hel1`):**
   You cannot rescale a server across locations. If a temporary seat is taken
   in `hel1` and the long-term target is `fsn1`, moving to `fsn1` requires
   creating a new server in `fsn1` and migrating via snapshot or application
   redeploy.
2. **Same CPU architecture (`x86` <-> `x86`, `arm` <-> `arm`):**
   `CX`, `CPX`, and `CCX` (`x86`) can rescale between one another in the same
   location, whereas `CAX` (`arm`) can only rescale to other `CAX` tiers.
3. **Disk size cannot shrink during a full rescale:**
   A full rescale requires `target_disk >= current_disk`. For example, if a
   server starts on `cpx22` (80 GB disk) in `fsn1`, it **can** rescale in place
   to `cx33` (80 GB) or `cx43` (160 GB) in `fsn1`, but it **cannot** shrink its
   disk down to `cx23` (40 GB) unless the earlier upgrade was performed with
   CPU/RAM-only rescaling (preserving a 40 GB disk).

## 5. Rate-limit-safe stock radar and agent sniping

Because `cx43`, `cx33`, and `cx23` in Germany (`fsn1`, `nbg1`) and Finland
(`hel1`) are in high demand, capacity frequently flips between
`available=false` and `available=true` for brief windows when other customers
delete or rescale servers.

### Catalog `available=false` indicators vs. live API placement (`POST /v1/servers`)

Hetzner Cloud has two distinct capacity layers:

1. **The Catalog Indicator (`GET /v1/server_types` -> `locations[].available`):**
   This boolean powers the Web Console UI's unavailable state in the browser.
   It is a cached, conservative indicator that can remain `false` even when
   physical hypervisor slots exist in the datacenter.
2. **The Live Placement Engine (`POST /v1/servers` via `hcloud server create` and `change_type`):**
   When an API provisioning request (`hcloud server create`) or an in-place
   rescale (`hcloud server change-type`) is submitted, the backend placement
   scheduler checks live hypervisor capacity directly. A tier that reports
   `available=false` in the catalog can still be allocated by the placement
   API when host slots are free.

The agent workflow uses a **two-layer strategy** (also emitted in `radar` JSON
under `cto_strategy`):

- **Layer 1 — Direct API Placement (`--allow-unavailable`):**
  Before waiting in a poll loop, pass `--allow-unavailable` to
  `legends-hetzner server create` (or `server snipe`). This still enforces all
  9 non-capacity safety checks (name, type, location, image, SSH keys, support,
  deprecation, and architecture), bypasses the cached `available=false` catalog
  flag, and sends one real `hcloud server create` request to the live placement
  engine. If the hypervisor has a slot, the server is created immediately; if
  the placement engine has no slots, the API returns `resource_unavailable`
  cleanly with no charge.
- **Layer 2 — Rate-Limit-Safe Watch (`radar --watch` / `server snipe`):**
  When direct API placement returns `resource_unavailable` or when watching
  passively until the catalog flips to `available=true`, use the bounded,
  jittered watch loop (`--interval >= 30`s).

### Why polling calibration matters

Hammering the Hetzner API every few seconds is counterproductive: Hetzner
enforces hourly request budgets (`RateLimit-Limit`, `RateLimit-Remaining`,
HTTP `429`), and aggressive loops risk throttling your API token right when a
seat opens.

`legends-hetzner` enforces polite, rate-limit-safe bounds in code:

- **Minimum poll interval:** `30` seconds (`--interval`, default `60` seconds,
  maximum `3600` seconds). Any `--interval` below `30` is rejected with
  `RADAR_INTERVAL_TOO_LOW` (exit 2).
- **Random positive jitter:** `--jitter` (default `10` seconds, range `0..60`)
  adds random delay to each poll interval so multiple agents never synchronize
  into thundering-herd spikes.
- **Bounded watch window:** `--max-polls` (default `30` polls when watching,
  maximum `120`) guarantees every watch or snipe run terminates cleanly rather
  than running an unbounded infinite loop.
- **Automatic REST availability enrichment for `hcloud 1.61.0`:** Older
  `hcloud` builds (such as `1.61.0`) omit `locations[].available` and
  `category` from `hcloud server-type list -o json`. When running against an
  older `hcloud` binary, `legends-hetzner` enriches `server-type list`
  read-only from the official `GET https://api.hetzner.cloud/v1/server_types`
  endpoint using the active auth selection so `radar`, `preflight`, and
  `server snipe` always see live `available=true/false` state.

### Workflow A: Read-only stock sweep and watch (`legends-hetzner radar`)

Check all Cost-Optimized tiers across `fsn1`, `nbg1`, and `hel1` in one shot:

```console
legends-hetzner --context my-project radar
```

Filter to German locations (`fsn1,nbg1`) and `x86` tiers in CTO priority order,
or watch politely until any matching seat opens:

```console
legends-hetzner --context my-project radar --germany-only --arch x86 --types cx43,cx33,cx23
legends-hetzner --context my-project radar --germany-only --arch x86 --types cx43,cx33 --watch --interval 60 --jitter 10 --max-polls 30
```

- Without `--watch`, `radar` performs a single read-only check and exits `0`.
- With `--watch`, `radar` exits `0` immediately on the first poll where at
  least one matching `(server_type, location)` reports `available=true`, or
  exits `3` if the bounded watch window finishes with `available_count: 0`.

### Workflow B: Guarded plan sniping (`legends-hetzner server snipe`)

When you have owner authorization to provision a specific target (for example
`cx43` or `cx33` in `fsn1`) as soon as capacity opens:

1. **Create the immutable plan offline:**

   ```console
   legends-hetzner --context my-project server plan --name app-prod-fsn1 --type cx43 --location fsn1 --image ubuntu-24.04 --ssh-key my-key --out ./plan-cx43-fsn1.json
   ```

2. **Rehearse with `--dry-run` first:**

   ```console
   legends-hetzner --context my-project server snipe --plan ./plan-cx43-fsn1.json --plan-hash sha256:REVIEWED_HASH --approve --dry-run --interval 60 --jitter 10 --max-polls 5
   ```

3. **Run the guarded live snipe (when authorized for paid creation):**

   ```console
   legends-hetzner --context my-project server snipe --plan ./plan-cx43-fsn1.json --plan-hash sha256:REVIEWED_HASH --approve --interval 60 --jitter 10 --max-polls 30 --receipt ./receipt-cx43-fsn1.json
   ```

How `server snipe` protects the project:

- **Fails fast on configuration errors:** If any non-capacity preflight check
  fails on poll 1 (such as a duplicate server name, missing SSH key, deprecated
  image, or architecture mismatch), `server snipe` aborts immediately (`exit 3`)
  without sleeping or polling.
- **Zero writes while waiting:** While `location_available` is `false`, only
  read-only preflight probes run.
- **Requires confirmed `available=true`:** Unknown availability never triggers
  a snipe write.
- **Single-invocation create:** The moment all 10 preflight checks pass,
  `server snipe` executes at most **one** `hcloud server create` call, runs
  readback verification, writes the redacted receipt (including `snipe` poll
  metadata), and exits. It never retries a failed or uncertain write.
