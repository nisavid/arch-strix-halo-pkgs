# llama.cpp-hip-gfx1151

## Maintenance Snapshot

- Role: `backend-runtime`
- Recipe package key: `llamacpp`
- Scaffold template: `llama-cpp`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/ggml-org/llama.cpp.git`
- Package version: `b8966`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `34`
- Recipe dependencies: `therock`
- Recorded reference packages: `aur/llama.cpp-hip, aur/llama.cpp`
- Authoritative reference package: `aur/llama.cpp-hip`
- Advisory reference packages: `aur/llama.cpp`
- Applied source patch files/actions: `0`

## Recipe notes

llama.cpp built with TWO backends for Lemonade:

Source lane: keep this package pinned to an audited upstream commit tarball.
When opening an update lane, repin to plain ggml-org/llama.cpp upstream
instead of reviving a stale local "head-apex" side branch.

ROCm (hipBLAS): Primary backend. Best prefill <32K context. Uses
amdclang from TheRock with full Zen 5 + gfx1151 HIP optimization flags,
explicit ggml LTO, and builds llama.cpp's server target. Binaries are
placed where Lemonade SDK expects them.

Vulkan: Secondary backend. +22% generation speed (44 vs 39 tok/s)
and handles >32K context prefill (no VMM limitation on gfx1151).
Uses the planned stable-diffusion.cpp Vulkan lane's amdclang, Zen 5,
ThinLTO, AOCL-LibM, and Vulkan release-mode flag shape; the
stable-diffusion.cpp package itself remains a separate backlog item.

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
- On 2026-04-24, reviewed upstream llama.cpp b8925 at 0adede866ddb2e31992b3792eaea31d18ed89acf and AUR llama.cpp-hip b8925-1. The b8911..b8925 range adds parser structured-output fixes, server SWA-full and cache-idle-slots cleanup, Jinja warning fixes, WebGPU FlashAttention work, Metal device logging, and Hexagon/Snapdragon updates. Record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-25, reviewed upstream llama.cpp b8929 at 9d34231bb89590ee760ae19ba665e7855cd4fd4e. The b8925..b8929 range changes SYCL, WebGPU SSM_SCAN, docs, and llama-quant's default quantization type from Q5_1 to Q8_0; no HIP/Vulkan package-build touchpoint was found. Record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-26, reviewed upstream llama.cpp b8935 at f454bd7eb8944629aabca163ea1c6e67e53fd77e and AUR llama.cpp-hip b8933-1. The b8929..b8935 range adds OpenCL IQ4_NL support, reduces CUDA MMQ stream-k overhead, optimizes Metal Tensor API usage, guards a Hexagon HMX clock request, fixes chat reasoning-marker spacing, and tightens speculative vocab compatibility checks. No HIP or Vulkan package-build touchpoint was found; record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-28, reviewed upstream llama.cpp b8953 at 434b2a1ff6a73927f1aeef1455599fbe207f7d6f and AUR llama.cpp-hip b8953-1. The b8935..b8953 range adds WebGPU Q1_0 and matmul tuning, fast i-quant mat-vec kernels, CPU/AMX optimizations, q8_0 download preference, model conversion cleanup, Qwen/LLaMA duplicate-scale removal, server router form-data forwarding, and Windows RPC/cache fixes. No HIP or Vulkan package-build touchpoint was found; record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-28, adopted upstream llama.cpp b8955 at 14e733e36f5752f39494b6c7e88022e43c05729a. The b8953..b8955 range refactors speculative decoding parameters, switches server m-rope task handling to pos_next, and updates argument parser, server, lookup, speculative, and llama-bench sources; no local packaging patch carry changed.
- On 2026-04-29, adopted upstream llama.cpp b8966 at 7b8443ac786c06438e0f407b7adaa72c220b5099. The b8955..b8966 range adds CANN operator work, backend/device duplicate-registration handling, Vulkan timestamp-barrier and shader/header fixes, WebGPU SSM scan aliasing fixes, CUDA FA support for Mistral Small head sizes, and a broad server UI tool/chat settings refactor; no local packaging patch carry changed.
- Keep the backend-specific package split explicit until benchmarking proves a routing wrapper is worth maintaining.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
