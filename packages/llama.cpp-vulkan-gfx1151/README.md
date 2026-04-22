# llama.cpp-vulkan-gfx1151

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
- Recorded reference packages: `aur/llama.cpp-vulkan-bin, aur/llama.cpp`
- Authoritative reference package: `aur/llama.cpp-vulkan-bin`
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

- Vulkan backend package; backend-specific runtime package, no shared common package in first pass.
- Closest current Vulkan reference: AUR llama.cpp-vulkan-bin for backend-specific packaging expectations, with generic AUR llama.cpp kept as the source-build advisory baseline.
- llama.cpp b8881 still includes SPIR-V headers directly from ggml-vulkan.cpp, so source builds require spirv-headers in addition to shaderc and vulkan-headers.
- Pinned to a concrete upstream commit tarball so the first-pass metadata stays reproducible without a full Git history clone.
- This scaffold still uses amdclang from rocm-llvm-gfx1151 for consistency with the recipe toolchain even though the Vulkan build does not use HIP offload.

## Intentional Divergences

- Uses a source-build path even though the closest backend-specific AUR reference is currently a binary package.
- Keeps the recipe's amdclang and ThinLTO lane for consistency with the rest of the stack while using Vulkan rather than HIP.

## Update Notes

- If a maintained source-built aur/llama.cpp-vulkan package appears, switch to it as the authoritative baseline.
- On 2026-04-22, reviewed upstream llama.cpp b8882 at ca7f7b7b947842384cd8dda4a17a1868f1493a3e. The b8881..b8882 range only adds WebGPU conv2d shader support under `ggml/src/ggml-webgpu`, outside the maintained HIP and Vulkan backend package outputs. Record freshness b8882 without repinning the package source until a supported backend diff or planned rebuild lane exists.
- Until then, compare runtime/package expectations against the -bin package and source-build conventions against aur/llama.cpp.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
