# arch-strix-halo-pkgs

Arch packaging for a Strix Halo local inference stack on Arch and CachyOS.

This repository turns a fast-moving ROCm, vLLM, `llama.cpp`, and Lemonade
setup into something you can inspect, rebuild, publish, install, and repair
with normal Arch package tools. It is a source and policy workspace, not a
binary package release.

> [!NOTE]
> The packages here are tuned and validated on a Strix Halo reference host with
> a Radeon 8060S (`gfx1151`). If stock Arch, CachyOS, AUR, or vendor packages
> already give you the behavior you need, start there. This repo is for the
> narrower case where you want the Strix Halo-specific package stack and its
> patch history.

## Why This Exists

Local inference stacks are easy to assemble once and hard to keep coherent.
This repo keeps the moving parts visible:

- ROCm and TheRock split packages for the `gfx1151` runtime and compiler lane
- source-built and rebuilt Python packages for the vLLM runtime closure
- `llama.cpp` HIP and Vulkan backends packaged as system-managed runtimes
- Lemonade server/app packages wired to those packaged backends
- package metadata, patch files, freshness checks, and validation notes that a
  maintainer can audit without chat history

The goal is not to hide complexity. The goal is to put each decision where it
can be reviewed: source patches beside packages, update policy under `docs/`,
package state in maintainer docs, and host validation in tracked scenarios.

## Who This Is For

- **Strix Halo users on Arch-family systems** who want a local package repo for
  ROCm, vLLM, `llama.cpp`, and Lemonade instead of one-off build directories.
- **Packagers and maintainers** who want to compare the local stack against
  Arch, CachyOS, AUR, upstream ROCm, and Blackcat Informatics recipe inputs.
- **Future agents** continuing this repo who need durable package context,
  current blockers, and exact update rules.

This is not a turnkey installer for every AMD GPU. It is a packaging workspace
for one hardware lane, with enough documentation to explain how the lane is
assembled and where it diverges.

## What It Packages

The stack currently includes these major layers:

| Layer | Package examples | Current lane |
| --- | --- | --- |
| ROCm foundation | `therock-gfx1151`, `rocm-gfx1151`, split ROCm libraries | TheRock `7.13` prerelease lane for `gfx1151` |
| Host math and Python | `aocl-utils-gfx1151`, `aocl-libm-gfx1151`, `python-gfx1151` | AOCL `5.2.2`, Python `3.14.4` |
| ML runtime | `python-pytorch-opt-rocm-gfx1151`, `python-triton-gfx1151`, `python-aotriton-gfx1151` | ROCm PyTorch `2.11`, ROCm Triton main-perf, AOTriton `0.11.2b` |
| Inference engines | `python-vllm-rocm-gfx1151`, `python-amd-aiter-gfx1151`, `python-flash-attn-rocm-gfx1151` | vLLM `0.19.1`, AITER post-`0.1.12.post1`, ROCm FlashAttention `2.8.4` |
| Graph and quantization experiments | `python-torchao-rocm-gfx1151`, `python-torch-migraphx-gfx1151` | TorchAO `0.17.0`, Torch-MIGraphX `1.2` |
| Model runners | `llama.cpp-hip-gfx1151`, `llama.cpp-vulkan-gfx1151` | packaged HIP and Vulkan backends from validated upstream snapshots |
| Frontend and service layer | `lemonade`, `lemonade-server`, `lemonade-app` | Lemonade `10.2.0` with packaged backend discovery |

Hand-maintained recipe packages carry package-local READMEs and `recipe.json`
files with exact baselines, patch notes, and update hints. The generated
TheRock package base has its own manifest and file-list evidence instead. Start
at [packages/](packages/) when you want package-specific details.

## What Makes It Different

This repo is not a verbatim mirror of existing Arch or AUR packages. It carries
Strix Halo-specific policy across the stack:

- `gfx1151` ROCm targeting and TheRock split-package rendering
- `amdclang` and Zen 5 tuned build lanes where they are useful
- concrete `llama.cpp` HIP tuning such as `-O3`, `-march=native`, ThinLTO,
  `-mprefer-vector-width=512`, `-famd-opt`, `gfx1151` HIP offload targeting,
  AMDGPU LLVM tuning, and optional LLVM inlining or Polly flags when the active
  compiler accepts them
- package-level replacements for runtime downloads, especially for Lemonade and
  `llama.cpp`
- Python `3.14` compatibility patches for packages whose upstream stable lanes
  are not there yet
- vLLM, AITER, FlashAttention, TorchAO, and Torch-MIGraphX patches that are
  tied to local ROCm behavior and host validation
- freshness and validation records that distinguish built, installed, passing,
  blocked, and merely advisory work

The patch overview is in [docs/patches.md](docs/patches.md). Current validated
state and known blockers are in [docs/maintainers/current-state.md](docs/maintainers/current-state.md)
and [docs/backlog.md](docs/backlog.md).

## Quick Start

Clone with submodules so the recipe input is available:

```bash
git clone --recurse-submodules https://github.com/nisavid/arch-strix-halo-pkgs.git
cd arch-strix-halo-pkgs
```

Then choose the path that matches your role.

### I Want To Install Built Packages

This repository does not commit binary package archives. If `repo/x86_64` has
already been populated on your machine, publish it to a world-traversable local
pacman repo and enable that repo in pacman:

```bash
sudo install -d /srv/pacman/strix-halo-gfx1151/x86_64
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
```

Then add the pacman stanza and install packages using the steps in the
[local repo guide](docs/usage/local-repo.md). A typical install target is:

```bash
paru -S rocm-gfx1151 python-vllm-rocm-gfx1151 llama.cpp-hip-gfx1151 lemonade
```

### I Want To Build Or Refresh Packages

Use ordinary package tools for a single package:

```bash
(cd packages/<pkgname> && makepkg -f)
python tools/update_pacman_repo.py \
  --package-dir packages/<pkgname> \
  --repo-dir repo/x86_64 \
  --require-packagelist
```

Use `amerge` when you want one command to plan, build, publish, and install a
selected package set:

```bash
tools/amerge run python-vllm-rocm-gfx1151 llama.cpp-hip-gfx1151 lemonade
```

See [Local Repo Usage](docs/usage/local-repo.md) for publish, repair, preview,
resume, and inference-smoke workflows.

### I Want To Understand The Repo

- [Documentation index](docs/README.md) orients you by task and audience.
- [Current state](docs/maintainers/current-state.md) records what is installed,
  validated, blocked, or merely planned.
- [Backlog](docs/backlog.md) records active follow-up work.
- [Patch inventory](docs/patches.md) explains the notable source changes.
- [TheRock generator architecture](docs/architecture/therock-generator.md)
  explains the generated ROCm split packages.

## Validation Story

The reference host has completed a full live cutover to the split ROCm stack
and subsequent native rebuilds through `tools/amerge`. Tracked smokes cover
ROCm visibility, Python imports, vLLM imports, `llama.cpp` entrypoints,
Lemonade entrypoints, selected pooling/reranking flows, Qwen server routes,
FlashAttention direct gates, and Torch-MIGraphX PT2E/Dynamo probes.

Some lanes are intentionally marked blocked or exploratory. For example, the
FlashAttention CK direct package surface is validated, while the vLLM Qwen CK
consumer path remains blocked in CK paged-KV behavior. The docs record that
boundary so the next maintainer does not rediscover it from terminal scrollback.

## Repository Map

| Path | Purpose |
| --- | --- |
| `packages/` | Package directories, PKGBUILDs, package-local READMEs, recipes, and patches |
| `policies/` | Render and freshness policy used to keep package metadata reproducible |
| `tools/` | Repo maintenance tools, including `amerge`, package renderers, freshness checks, and inference smokes |
| `generators/` | TheRock split-package generation code |
| `inference/scenarios/` | Tracked local inference scenario catalog |
| `docs/` | User, maintainer, architecture, policy, state, and backlog documentation |
| `upstream/ai-notes/` | Blackcat Informatics recipe input submodule |

## Upstream And Baseline Inputs

This repo builds on work from:

- [Blackcat Informatics' Strix Halo recipe work](https://github.com/paudley/ai-notes/tree/main/strix-halo)
- [TheRock](https://github.com/ROCm/TheRock)
- [ROCm](https://github.com/ROCm/ROCm)
- [ROCm PyTorch](https://github.com/ROCm/pytorch)
- [ROCm Triton](https://github.com/ROCm/triton)
- [AOTriton](https://github.com/ROCm/aotriton)
- [AITER](https://github.com/ROCm/aiter)
- [ROCm FlashAttention](https://github.com/ROCm/flash-attention)
- [vLLM](https://github.com/vllm-project/vllm)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [Lemonade](https://github.com/lemonade-sdk/lemonade)
- Arch, CachyOS, and AUR package metadata used as package baselines
