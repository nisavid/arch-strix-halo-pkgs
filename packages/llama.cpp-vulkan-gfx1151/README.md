# llama.cpp-vulkan-gfx1151

## Maintenance Snapshot

- Role: `backend-runtime`
- Recipe package key: `llamacpp`
- Scaffold template: `llama-cpp`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/ggml-org/llama.cpp.git`
- Package version: `b8911`
- Recipe revision: `a188f9e (20260424, 10 path commits)`
- Recipe steps: `34`
- Recipe dependencies: `therock`
- Recorded reference packages: `aur/llama.cpp-vulkan-bin, aur/llama.cpp`
- Authoritative reference package: `aur/llama.cpp-vulkan-bin`
- Advisory reference packages: `aur/llama.cpp`
- Applied source patch files/actions: `0`

## Recipe notes

llama.cpp built with TWO backends for Lemonade:

Source branch: upstream master. APEX GGUF support is expected on current
upstream HEAD, so step 33 should build plain ggml-org/llama.cpp rather
than a stale local "head-apex" side branch.

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
- Vulkan source builds require spirv-headers in addition to shaderc and vulkan-headers.
- Pinned to a concrete upstream commit tarball so the first-pass metadata stays reproducible without a full Git history clone.
- This scaffold still uses amdclang from rocm-llvm-gfx1151 for consistency with the recipe toolchain even though the Vulkan build does not use HIP offload.

## Intentional Divergences

- Uses a source-build path even though the closest backend-specific AUR reference is currently a binary package.
- Keeps the recipe's amdclang and ThinLTO lane for consistency with the rest of the stack while using Vulkan rather than HIP.

## Update Notes

- If a maintained source-built aur/llama.cpp-vulkan package appears, switch to it as the authoritative baseline.
- On 2026-04-23, adopted upstream llama.cpp b8911 at 5d2b52d80d9f375a6e81d07e212d047d8ee4f76e. The b8892..b8911 range updates shared server/API handling, fixes CVE-2026-21869 negative n_discard handling, updates ModelOpt mixed-precision GGUF conversion, and adds WebGPU/SYCL/Snapdragon work; no Vulkan-specific build-system change was found, but the server/tool source delta is relevant to the packaged runtime.
- On 2026-04-24, reviewed upstream llama.cpp b8925 at 0adede866ddb2e31992b3792eaea31d18ed89acf. The b8911..b8925 range adds parser structured-output fixes, server SWA-full and cache-idle-slots cleanup, Jinja warning fixes, WebGPU FlashAttention work, Metal device logging, and Hexagon/Snapdragon updates. Record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-25, reviewed upstream llama.cpp b8929 at 9d34231bb89590ee760ae19ba665e7855cd4fd4e. The b8925..b8929 range changes SYCL, WebGPU SSM_SCAN, docs, and llama-quant's default quantization type from Q5_1 to Q8_0; no Vulkan package-build touchpoint was found. Record it as reviewed without repinning until a runtime rebuild lane is opened.
- Until then, compare runtime/package expectations against the -bin package and source-build conventions against aur/llama.cpp.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
