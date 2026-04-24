# llama.cpp-hip-gfx1151

## Maintenance Snapshot

- Role: `backend-runtime`
- Recipe package key: `llamacpp`
- Scaffold template: `llama-cpp`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/ggml-org/llama.cpp.git`
- Package version: `b8911`
- Recipe revision: `b453c33 (20260422, 9 path commits)`
- Recipe steps: `33`
- Recipe dependencies: `therock`
- Recorded reference packages: `aur/llama.cpp-hip, aur/llama.cpp`
- Authoritative reference package: `aur/llama.cpp-hip`
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

- ROCm/hip backend package; backend-specific runtime package, no shared common package in first pass.
- Authoritative base: AUR llama.cpp-hip, because it is the closest maintained ROCm packaging lane for llama.cpp on Arch.
- Advisory reference: generic AUR llama.cpp for shared install/dependency conventions outside the ROCm-specific package split.
- Pinned to a concrete upstream commit tarball so the first-pass metadata stays reproducible without a full Git history clone.

## Intentional Divergences

- Installs into /opt/llama.cpp-hip-gfx1151 with suffixed wrapper binaries instead of taking over the generic /usr/bin names directly.
- Uses the recipe's amdclang plus gfx1151-targeted HIP build lane and private-library RPATH handling.

## Update Notes

- Diff against aur/llama.cpp-hip first during updates, then consult aur/llama.cpp for shared install/dependency conventions outside the ROCm-specific split.
- On 2026-04-23, adopted upstream llama.cpp b8911 at 5d2b52d80d9f375a6e81d07e212d047d8ee4f76e. The b8892..b8911 range flips HIP graphs on by default, fixes server handling for LFM2-Audio transcriptions, Anthropic prefix caching and chat_template_kwargs forwarding, fixes CVE-2026-21869 negative n_discard handling, and updates ModelOpt mixed-precision GGUF conversion; no local packaging patch carry changed.
- Keep the backend-specific package split explicit until benchmarking proves a routing wrapper is worth maintaining.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
