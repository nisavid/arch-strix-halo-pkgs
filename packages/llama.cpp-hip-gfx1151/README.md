# llama.cpp-hip-gfx1151

## Maintenance Snapshot

- Role: `backend-runtime`
- Recipe package key: `llamacpp`
- Scaffold template: `llama-cpp`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/ggml-org/llama.cpp.git`
- Package version: `b8881`
- Recipe revision: `ad42886 (20260317, 8 path commits)`
- Recipe steps: `33`
- Recipe dependencies: `therock`
- Recorded reference packages: `aur/llama.cpp-hip, aur/llama.cpp`
- Authoritative reference package: `aur/llama.cpp-hip`
- Advisory reference packages: `aur/llama.cpp`
- Applied source patch files/actions: `0`

## Recipe notes

llama.cpp built with TWO backends for Lemonade:

ROCm (hipBLAS): Primary backend. Best prefill <32K context. Uses
amdclang from TheRock with full Zen 5 + gfx1151 HIP optimization
flags. Binaries placed where Lemonade SDK expects them.

Vulkan: Secondary backend. +22% generation speed (44 vs 39 tok/s)
and handles >32K context prefill (no VMM limitation on gfx1151).
CPU-only optimization flags, no HIP offload.

Both backends get .env files with gfx1151 runtime optimizations
(batch sizing, hipBLASLt, THP). RPATH patched via patchelf so
binaries find their shared libraries without LD_LIBRARY_PATH.

## Scaffold notes

- ROCm/hip backend package; backend-specific runtime package, no shared common package in first pass.
- Authoritative base: AUR llama.cpp-hip, because it is the closest maintained ROCm packaging lane for llama.cpp on Arch.
- Advisory reference: generic AUR llama.cpp for shared install/dependency conventions outside the ROCm-specific package split.
- Pinned to a concrete upstream commit tarball so the first-pass metadata stays reproducible without a full Git history clone.

## Intentional Divergences

- Installs into /opt/llama.cpp-hip-gfx1151 with suffixed wrapper binaries instead of taking over the generic /usr/bin names directly.
- Uses the recipe's amdclang plus gfx1151-targeted HIP build lane and private-library RPATH handling.

## Update Notes

- Diff against aur/llama.cpp-hip first during updates, then consult aur/llama.cpp for shared install/dependency conventions outside the ROCm-specific split.
- On 2026-04-22, reviewed upstream llama.cpp b8882 at ca7f7b7b947842384cd8dda4a17a1868f1493a3e. The b8881..b8882 range only adds WebGPU conv2d shader support under `ggml/src/ggml-webgpu`, outside the maintained HIP and Vulkan backend package outputs. Record freshness b8882 without repinning the package source until a supported backend diff or planned rebuild lane exists.
- Keep the backend-specific package split explicit until benchmarking proves a routing wrapper is worth maintaining.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
