# arch-strix-halo-pkgs

Arch packaging for a Strix Halo local inference stack built around ROCm, vLLM,
`llama.cpp`, and Lemonade.

This repo brings several separate projects into one packageable Arch stack:

- AMD's ROCm and TheRock for the runtime and compiler toolchain
- Blackcat Informatics' Strix Halo recipe work as the hardware-specific build
  lane and tuning baseline
- Arch, CachyOS, and AUR package conventions for package shape, dependencies,
  and update expectations

The result is a local pacman repo that can install, upgrade, inspect, rebuild,
and benchmark the stack as packages instead of as a pile of one-off shell
commands.

It is developed and validated on a Strix Halo system running CachyOS.

## What It Packages

### Runtime Foundation

- TheRock-derived ROCm split packages on the `7.13` prerelease lane, built for
  `gfx1151`
- AOCL utilities and math libraries for the host side of the stack
- CPython `3.14.4` and selected rebuilt Python dependencies needed above it

### Python Model Runtime

- ROCm PyTorch `2.11`
- ROCm Triton `3.5.1`
- AOTriton `0.11.2b`
- AITER `0.1.0`
- vLLM `0.19.0`

### Model Runners

- `llama.cpp` `b8611` built in two flavors:
  - HIP for ROCm
  - Vulkan

### Frontend And Service Layer

- Lemonade `10.2.0`
- A local pacman repo layout for publishing and consuming the package set on an
  Arch system

## What It Changes

This is not a verbatim mirror of the usual Arch or AUR packages.

The repo carries Strix Halo–specific build policy across the stack, and the
`llama.cpp` packages in particular are built with an `amdclang`-based toolchain
and flags that are not typical of the generic Arch packages:

- `-O3`
- `-march=native`
- `-flto=thin`
- `-mprefer-vector-width=512`
- `-famd-opt`
- HIP-specific `gfx1151` offload targeting and AMDGPU LLVM tuning
- optional additional LLVM inlining and Polly flags when the active compiler
  accepts them

The repo also carries compatibility and integration patches that upstream source
trees do not currently provide in the form needed here:

- vLLM `0.19.0` Python `3.14` compatibility on the packaged stable lane
- AITER `gfx1151` header compatibility for RDNA 3.5
- Lemonade fixes for Linux XDNA2 detection on this class of system
- Lemonade changes so packaged HIP and Vulkan `llama.cpp` backends are treated
  as system-managed backends rather than runtime downloads

## Why Use This Instead Of The Usual Packages

If the stock Arch, CachyOS, or AUR packages already give you the behavior and
performance you want, use them.

This repo exists for the narrower case where you want a Strix Halo tuned stack
with explicit package policy, explicit patch carry, and a reproducible
local-repo workflow. Compared with mixing upstream wheels, runtime downloads,
and manual rebuilds, it gives you:

- a single package source for the whole stack
- patch files you can review and pick apart
- package metadata that records baselines, divergences, and update notes
- a straightforward path for benchmarking the stack against more standard Arch
  alternatives such as `aur/rocm-gfx1151-bin`

## Install It On Arch

The supported installation story is a local pacman repo published from this
repository.

1. Clone the repo and publish its package repo to `/srv/pacman`.

```bash
git clone --recurse-submodules https://github.com/nisavid/arch-strix-halo-pkgs.git
cd arch-strix-halo-pkgs
sudo install -d /srv/pacman/strix-halo-gfx1151/x86_64
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
```

2. Enable the local repo in pacman.

```bash
printf '%s\n' \
  '[strix-halo-gfx1151]' \
  'SigLevel = Optional TrustAll' \
  'Server = file:///srv/pacman/strix-halo-gfx1151/x86_64' \
  | sudo tee /etc/pacman.d/strix-halo-gfx1151.conf >/dev/null

grep -qxF 'Include = /etc/pacman.d/strix-halo-gfx1151.conf' /etc/pacman.conf \
  || echo 'Include = /etc/pacman.d/strix-halo-gfx1151.conf' \
  | sudo tee -a /etc/pacman.conf >/dev/null

sudo pacman -Sy
```

3. Install the stack you want to use.

```bash
paru -S rocm-gfx1151 python-vllm-rocm-gfx1151 llama.cpp-hip-gfx1151 lemonade
```

For the full publish, update, and repair workflow, use the
[local repo guide](docs/usage/local-repo.md).

If you already cloned without submodules and need the canonical recipe input
for scaffold rendering, run:

```bash
git submodule update --init --recursive
```

## Upstream Projects

This repo builds on:

- [Blackcat Informatics' Strix Halo recipe work](https://github.com/paudley/ai-notes/tree/main/strix-halo)
- [TheRock](https://github.com/ROCm/TheRock)
- [ROCm](https://github.com/ROCm/ROCm)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [Lemonade](https://github.com/lemonade-sdk/lemonade)
- [ROCm PyTorch](https://github.com/ROCm/pytorch)
- [ROCm Triton](https://github.com/ROCm/triton)
- [AOTriton](https://github.com/ROCm/aotriton)
- [vLLM](https://github.com/vllm-project/vllm)

## Current State

Implemented in the repo:

- the first complete packaged stack
- the local pacman repo workflow
- package-local maintenance metadata for update and audit work
- durable patch files for the main source-level deltas

Verified on the development machine:

- live cutover from the earlier monolithic ROCm replacement to the split stack
- `torch` import and GPU visibility
- `vllm` import
- both packaged `llama.cpp` backends
- Lemonade packaging and backend presentation, including system-managed HIP and
  Vulkan `llama.cpp` rows

Deferred follow-up work:

- benchmark the stack against `aur/rocm-gfx1151-bin`
- benchmark `llama.cpp` ROCm versus Vulkan across the preferred model set
- continue replacing remaining scripted source edits with package-local patches
- revisit FlyDSL once the MLIR packaging surface is good enough for a clean
  downstream package

For the deeper maintainer documentation, start at the [docs index](docs/README.md).

## License

This project is licensed under the [MIT License](LICENSE).
