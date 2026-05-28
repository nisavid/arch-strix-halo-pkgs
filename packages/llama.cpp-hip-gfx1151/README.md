# llama.cpp-hip-gfx1151

## Maintenance Snapshot

- Role: `backend-runtime`
- Recipe package key: `llamacpp`
- Scaffold template: `llama-cpp`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/ggml-org/llama.cpp.git`
- Package version: `b9371`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `34`
- Recipe dependencies: `therock`
- Recorded reference packages: `aur/llama.cpp-hip, aur/llama.cpp`
- Authoritative reference package: `aur/llama.cpp-hip`
- Advisory reference packages: `aur/llama.cpp`
- Applied source patch files/actions: `1`

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
- The selected-token logits patch adds a generic `token_logits` completion-request field and returns the requested raw logits in `token_logits`; model-specific token choices belong in downstream service configuration.

## Intentional Divergences

- Installs into /opt/llama.cpp-hip-gfx1151 with suffixed wrapper binaries instead of taking over the generic /usr/bin names directly.
- Uses the recipe's amdclang plus gfx1151-targeted HIP build lane and private-library RPATH handling.
- Carries a server-local selected-token logits extension for completion requests so downstream rerank adapters can request raw logits for explicit token IDs without using llama.cpp's native rerank endpoint.

## Update Notes

- Diff against aur/llama.cpp-hip first during updates, then consult aur/llama.cpp for shared install/dependency conventions outside the ROCm-specific split.
- On 2026-04-23, adopted upstream llama.cpp b8911 at 5d2b52d80d9f375a6e81d07e212d047d8ee4f76e. The b8892..b8911 range flips HIP graphs on by default, fixes server handling for LFM2-Audio transcriptions, Anthropic prefix caching and chat_template_kwargs forwarding, fixes CVE-2026-21869 negative n_discard handling, and updates ModelOpt mixed-precision GGUF conversion; no local packaging patch carry changed.
- On 2026-04-24, reviewed upstream llama.cpp b8925 at 0adede866ddb2e31992b3792eaea31d18ed89acf and AUR llama.cpp-hip b8925-1. The b8911..b8925 range adds parser structured-output fixes, server SWA-full and cache-idle-slots cleanup, Jinja warning fixes, WebGPU FlashAttention work, Metal device logging, and Hexagon/Snapdragon updates. Record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-25, reviewed upstream llama.cpp b8929 at 9d34231bb89590ee760ae19ba665e7855cd4fd4e. The b8925..b8929 range changes SYCL, WebGPU SSM_SCAN, docs, and llama-quant's default quantization type from Q5_1 to Q8_0; no HIP/Vulkan package-build touchpoint was found. Record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-26, reviewed upstream llama.cpp b8935 at f454bd7eb8944629aabca163ea1c6e67e53fd77e and AUR llama.cpp-hip b8933-1. The b8929..b8935 range adds OpenCL IQ4_NL support, reduces CUDA MMQ stream-k overhead, optimizes Metal Tensor API usage, guards a Hexagon HMX clock request, fixes chat reasoning-marker spacing, and tightens speculative vocab compatibility checks. No HIP or Vulkan package-build touchpoint was found; record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-28, reviewed upstream llama.cpp b8953 at 434b2a1ff6a73927f1aeef1455599fbe207f7d6f and AUR llama.cpp-hip b8953-1. The b8935..b8953 range adds WebGPU Q1_0 and matmul tuning, fast i-quant mat-vec kernels, CPU/AMX optimizations, q8_0 download preference, model conversion cleanup, Qwen/LLaMA duplicate-scale removal, server router form-data forwarding, and Windows RPC/cache fixes. No HIP or Vulkan package-build touchpoint was found; record it as reviewed without repinning until a runtime rebuild lane is opened.
- On 2026-04-28, adopted upstream llama.cpp b8955 at 14e733e36f5752f39494b6c7e88022e43c05729a. The b8953..b8955 range refactors speculative decoding parameters, switches server m-rope task handling to pos_next, and updates argument parser, server, lookup, speculative, and llama-bench sources; no local packaging patch carry changed.
- On 2026-04-29, adopted upstream llama.cpp b8966 at 7b8443ac786c06438e0f407b7adaa72c220b5099. The b8955..b8966 range adds CANN operator work, backend/device duplicate-registration handling, Vulkan timestamp-barrier and shader/header fixes, WebGPU SSM scan aliasing fixes, CUDA FA support for Mistral Small head sizes, and a broad server UI tool/chat settings refactor; no local packaging patch carry changed.
- On 2026-05-01, adopted upstream llama.cpp b8992 at 5cbfb18075c95437e4ac7fb50e3baf88fe137a87. The b8966..b8992 range is runtime-facing for the packaged backends: common sampling, speculative, reasoning-budget, server/Web UI, ggml 0.10.1, Vulkan tensor-helper, mmap ftello/fseeko, hf-cache null-user, and cpp-httplib vendor changes.
- On 2026-05-03, adopted upstream llama.cpp b9010 at d05fe1d7dadbf8943c8f1903fcf65b935ddab839. The b8992..b9010 range changes shared runtime/server code, ggml 0.10.2, Vulkan FlashAttention coopmat2 support, OpenCL MXFP4 MoE support, WebGPU shaders, and server UI attachment/refactor paths; no local package patch carry changed.
- On 2026-05-10, adopted upstream llama.cpp b9101 at 389ff61d77b5c71cec0cf92fe4e5d01ace80b797. The b9010..b9101 range includes shared runtime/server changes, ggml 0.11.1, model architecture fixes, Gemma4_26B_A4B_NVFP4 support, Vulkan code changes, and cpp-httplib updates that overlap the packaged HIP, Vulkan, and Lemonade runtime lanes.
- On 2026-05-14, adopted upstream llama.cpp b9145 at 9ed6e19b9d7e14a71a19622287b2dcd495a828b8. The b9101..b9145 range includes shared runtime/server changes, speculative parallel drafting support, modalities surfaced from /v1/models, cpp-httplib 0.44.0, ggml/CMake updates, and Vulkan asymmetric FlashAttention and shared-memory checks that overlap the packaged HIP, Vulkan, and Lemonade runtime lanes.
- On 2026-05-15, adopted upstream llama.cpp b9165 at 769cc93a43b51bf6013986180c73ee60cf24cede. The b9145..b9165 range includes HIP RDNA3 MMA/transpose tuning, Vulkan integer pipeline selection, WebUI streaming/error handling, Codex CLI Responses-tool compatibility, Qwen tokenizer handling, and release-archive fixes that overlap the packaged HIP, Vulkan, server, and Lemonade runtime lanes.
- On 2026-05-19, adopted upstream llama.cpp b9222 at 9a532ae4bab1b164052ce60a738f78538b421c66. The b9165..b9222 range includes ggml 0.12.0, MTP support, server/Web UI updates, Vulkan BF16/ROPE/SSM pipeline work, and removal of the old Hugging Face cache migration path, so both packaged backends and Lemonade backend metadata follow the same source snapshot.
- On 2026-05-26, adopted upstream llama.cpp b9330 at 328874d054e0eb44591202a23c209cf02c18e3cb. The b9222..b9330 range includes server MTP and draft-resource fixes, prompt token counts in /slots, CMake/UI build refactors, ggml 0.13.0, Vulkan im2col and snake activation updates, and backend probe fixes including ffn_latent MUL_MAT classification, so both packaged backends and Lemonade backend metadata follow the same source snapshot.
- On 2026-05-27, updated the package source to upstream llama.cpp b9352 at b4c0549a49be9e6dc59ac9d0a5bc21dbda910774. The b9330..b9352 range includes Vulkan conv2d and coopmat1 work, SYCL pool VMM support, WebGPU MMVQ cleanup, Talkie/Mistral3 model metadata, Hexagon CONCAT/ROPE work, CUDA FWHT sync fixes, and CI workflow refactors; no server patch-carry file changed, but the Vulkan runtime delta and shared model/runtime movement justify refreshing both packaged backends and Lemonade backend metadata.
- On 2026-05-28, updated the package source to upstream llama.cpp b9357 at 4d8cc0c56ffba3f8b7fdb0130627fed2a6f71958. The b9352..b9357 range adds MiniCPM5 tokenizer support, fixes the SSL listener log scheme, avoids preferring a dedicated Vulkan transfer queue on AMD UMA devices, and includes CI/docs maintenance. The shared selected-token logits patch still applies cleanly to the unchanged server context/task files.
- On 2026-05-28, updated the package source to upstream llama.cpp b9371 at f12cc6d0fa96d6a3c33952f06b7439ac43a3c3fe. The b9357..b9371 range includes llama.cpp argument-environment name cleanup, cpp-httplib 0.46.0, Vulkan REPEAT/cooperative-matrix/vector-matmul work, WebGPU dispatch cleanup, Hexagon Q4_1 support, CUDA/CI/build maintenance, and conversion dependency metadata updates. The shared selected-token logits patch target files are unchanged, and direct git apply checking passed against b9371.
- Keep the backend-specific package split explicit until benchmarking proves a routing wrapper is worth maintaining.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
