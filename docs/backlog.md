# Backlog

## Packaging And Build Hygiene

- Newly discovered ROCm inference candidates from
  `docs/maintainers/rocm-inference-reference.md` belong near the top of this
  backlog, but they are not validated package commitments until their source
  audit and host gates pass.
  - Torch-MIGraphX PT2E follow-up: `python-torch-migraphx-gfx1151` now tracks
    FX lowering, PT2E quantizer imports, a bounded ResNet-style
    `torch.compile(..., backend="migraphx")` smoke, and a bounded PT2E
    ResNet-style smoke as installed-validated package/scenario lanes. Keep a
    full ResNet50 PT2E quantization flow as optional follow-up if its
    model/data dependencies are needed.
  - Package experiment: FlashAttention CK; source audit, package build, host
    install, direct CK import proof, and direct CK qkvpacked smoke pass for
    `python-flash-attn-rocm-gfx1151 2.8.4-2`. `2.8.4-10` is now
    installed-validated for direct import, qkvpacked, variable-length wrapper
    keywords, and the vLLM adapter surface. vLLM Qwen3.5 CK consumer work is
    blocked deeper in CK paged-KV: vLLM's hybrid path presents 64-token kernel
    pages by default, and diagnostics that force 128-divisible pages progress to
    a GPU memory-access fault inside CK. Do not promote the CK Qwen engine path
    without upstream CK paged-KV kernel repair or a different validated backend.
    The preserved closeout notes, source disposition, and future direct-CK test
    gates are in `docs/maintainers/flashattention-ck-paged-kv.md`.
  - Package experiment: FlashAttention Triton; `python-flash-attn-rocm-gfx1151`
    now has build proof, installed import proof, runtime backend-selection
    proof, and a bounded non-autotuned Triton AMD smoke from the installed
    package. The first vLLM consumer backend-selection gate also passed through
    `python-vllm-rocm-gfx1151` `0.19.1-4` and
    `vllm.flash-attn.triton-amd.vit-wrapper`. Treat
    `FLASH_ATTENTION_TRITON_AMD_AUTOTUNE=TRUE` as a later performance task.
  - Candidate follow-ups: Quark, AWQ, GPTQ, bitsandbytes, xFormers, and
    FBGEMM. Keep each marked as requires host validation and source audit
    before adding a package or promoting a scenario.
  - Existing affected failures audited on 2026-04-22: Qwen3.6 FP8 MoE remains
    blocked, Gemma 4 AITER FlashAttention remains blocked, and MIGraphX
    creates a separate compiled graph/quantization lane rather than a vLLM
    backend replacement.
- Rerender `hipfort-gfx1151` and `mivisionx-gfx1151` only after a fresh
  TheRock build or staged install contains those project payloads. Policy
  metadata and representative path aliases are now present, but the current
  live/staged payload and package artifacts do not contain either project.
- Revisit the TheRock split-package Arch/CachyOS baseline audit when Arch adds
  new package surfaces, CachyOS reshapes ROCm split-package metadata, or a
  staged TheRock root adds new payload packages. The current generated family
  is audited through the 2026-04-25 baseline pass; remaining non-matching names
  are recorded as local support exceptions in
  `docs/maintainers/therock-generator-status.md`.
- Convert remaining scripted source edits into durable patch files where
  practical. The first slice moved `python-triton-gfx1151`'s stabilized Python
  3.14, `-Werror`, and `AttrsDescriptor.__repr__` edits into package-local
  patches; the second moved `aocl-libm-gfx1151`'s SCons toolchain edits into a
  package-local patch; the third moved `python-pytorch-opt-rocm-gfx1151`'s
  NumPy target C-API, HIP clang ABI flag, and gfx1151 CK GEMM edits into
  package-local patches. Continue with other durable source mutations that
  still live as inline package edits.
- Tighten package hygiene for embedded build paths in PyTorch and vLLM.
- Fix `tools/render_recipe_scaffolds.py` before relying on it for
  `python-torchao-rocm-gfx1151` PKGBUILD regeneration. A 2026-04-19 render
  trial would have dropped the package's manual submodule initialization,
  `ROCM_HOME`, `PYTORCH_ROCM_ARCH`, `VERSION_SUFFIX`, and post-install RPATH
  logic, so package-local docs were updated narrowly instead.
- Keep the local `python-transformers-gfx1151` and
  `python-mistral-common-gfx1151` closure lanes aligned. The current Gemma 4
  processor path needs both `transformers.models.gemma4` and
  `mistral_common.protocol.instruct.request.ReasoningEffort`.
- Optionally harden vLLM's quoted `CMAKE_ARGS` parsing as build plumbing if a
  future package lane needs nested quoted CMake values. The current PKGBUILD
  uses direct `CFLAGS`, `CXXFLAGS`, and `HIPFLAGS` forwarding, and the
  post-rebuild `shlex.split(CMAKE_ARGS)` probe no longer reproduces the old
  gfx1151 `csrc/sampler.hip` compiler failure.
- Revisit full multimodal Gemma 4 serving on the `google/gemma-4-26B-A4B-it`
  lane. The current repo-owned local vLLM repair path is intentionally
  text-only with
  `--limit-mm-per-prompt {"image":0,"audio":0,"video":0}` because leaving
  `video` implicit was enough to send vLLM back into multimodal warmup and
  reproduce the earlier GPU memory-access fault during engine initialization on
  the reference host.
- Investigate non-eager Gemma 4 lanes before promoting any E2B compiled path.
  - keep the repo-owned helper defaults eager for E2B; 26B-A4B and 31B compiled
    probes have passed, but E2B compiled plus CUDAGraph still corrupts output
    and the no-CUDAGraph compiled path previously faulted during warmup
  - start from the `compiled-probe` scenarios under `inference/scenarios/`
    instead of treating the experiment as an ad hoc terminal-only rehearsal
- Continue Qwen3.6 FP8 MoE/shared-expert follow-up on gfx1151.
  - Qwen3.5 sampler/GDN package carry, tiny smoke coverage, and blocked-probe
    coverage for Qwen3.6 are already tracked and validated
  - validate the new dense FP8/Quark and GPTQ-Int4 exploratory probes before
    promoting either lane to smoke coverage:
    `vllm.qwen3.0_6b-fp8-kv.text.fp8-dense-quark` and
    `vllm.qwen2_5.0_5b-gptq-int4.text.basic`
  - compare FP8 probe outcomes against the accepted unquantized no-AITER
    `Qwen/Qwen3.6-35B-A3B` control, which currently passes with
    `--max-num-batched-tokens 32` and `--gpu-memory-utilization 0.9`
  - treat the non-AITER path as blocked until a backend advertises gfx1151 FP8
    MoE support; the current failure is
    `No FP8 MoE backend supports the deployment configuration`
  - treat the forced-AITER path as blocked on AITER opus/gfx1151 FP8-kernel
    feature work; the current `module_quant` failure is
    `unknown type name 'mfma_adaptor'`
  - do not paper over the AITER OPUS gap by selecting the gfx1250 WMMA path:
    gfx1151 rejects the relevant FP8 WMMA builtin with
    `needs target feature gfx1250-insts`. The current upstream AITER release
    has RDNA registration/config-selection work, but no small gfx11 OPUS FP8
    adaptor patch to carry locally.
  - keep the AxionML NVFP4 probe blocked on local ROCm vLLM ModelOpt FP4
    support; the checkpoint is ModelOpt NVFP4, and the current expected failure
    is `modelopt_fp4 quantization is currently not supported in rocm.`
  - treat Petit as out of scope for Strix Halo unless its support matrix
    changes beyond AMD CDNA2/CDNA3; the next plausible NVFP4 path is upstream
    vLLM/ROCm support for `modelopt_fp4` on ROCm or a different accepted
    checkpoint format, not a Petit backend patch for gfx1151.
- Follow up Qwen server coverage beyond the reduced local smokes.
  - all eight reduced Qwen3.6 server smokes now pass on the host
  - optionally add a tracked `ngram_gpu` speculative-decoding scenario; the
    one-off 2026-04-21 sweep passed with `prompt_lookup_min=2`,
    `prompt_lookup_max=5`, and `num_speculative_tokens=2`
  - keep CPU `ngram` blocked until its generation-time `EngineCore` death is
    explained or fixed
- Keep DFlash speculative decoding gated on a dedicated vLLM package update
  from the current local 0.19.1 source to a release with the merged DFlash
  support from PR #38300.
  - the local package should keep only the narrow speculators parser backport
    until the release source also includes the DFlash model, proposer/runtime,
    and registry integration
  - as of the 2026-04-28 freshness refresh, upstream `v0.20.0` is available
    and includes DFlash model/runtime pieces; adopt it only through a full vLLM
    package-update lane with patch refresh and host smokes
  - keep `draft_model` with `Qwen/Qwen3.5-0.8B` exploratory; current vLLM
    remaps that checkpoint into the Qwen3.5 MTP loader and fails on hidden-size
    mismatch instead of running a plain draft-model path
  - keep broader Qwen media sizes exploratory; the validated local media smoke
    bounds image dummy profiling to the tiny embedded fixture
  - keep GB200, MI355X, Qwen3.5 397B throughput, FP8 blocked paths, and full
    ultra-long-context recipe shapes advisory until local gfx1151 evidence
    justifies a narrower executable probe
- Only revisit Gemma 4 on AITER fused-MoE if there is a concrete reason to
  move off the current TRITON unquantized-MoE lane.
  - treat any such attempt as a fresh experiment
  - do not restore the dropped vLLM-side AITER MoE padding carry by default
- Revisit FlashAttention through AITER as a separate attention experiment when
  the backend lane needs another candidate.
  - use FlashAttention's AMD ROCm support notes as advisory input:
    <https://github.com/Dao-AILab/flash-attention#amd-rocm-support>
  - `python-flash-attn-rocm-gfx1151` now packages the ROCm FlashAttention
    `main_perf` AMD Triton path for `gfx1151`; it depends on the repo-owned
    AITER, Triton, and ROCm PyTorch packages instead of installing bundled AITER
  - keep this distinct from the Gemma 4 AITER fused-MoE lane
  - `vllm.gemma4.e2b.server.attn-aiter-fa-blocked` now tracks the current
    first gate: on 2026-04-20, forcing `ROCM_AITER_FA` failed before serving
    because vLLM reported `compute capability not supported`
  - current package evidence: `tools/amerge build python-flash-attn-rocm-gfx1151`
    builds `2.8.4-1`; `tools/amerge deploy python-flash-attn-rocm-gfx1151`
    installs it; the installed package imports `flash_attn`, selects AITER's
    Triton AMD backend with `FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`, and
    passes a bounded `flash_attn_qkvpacked_func` GPU smoke
  - the first vLLM consumer gate targets the ViT FlashAttention wrapper
    because vLLM's text decoder `FLASH_ATTN` path expects vLLM's own
    FlashAttention ABI and Gemma 4 still rejects forced `FLASH_ATTN` for its
    head shape; `python-vllm-rocm-gfx1151` `0.19.1-4` carries the ROCm platform
    detection fix, and `vllm.flash-attn.triton-amd.vit-wrapper` passed on the
    reference host
  - next gate: only broaden the consumer claim after a real model route needs
    FlashAttention Triton AMD and passes with the installed packages
  - treat `FLASH_ATTENTION_TRITON_AMD_AUTOTUNE="TRUE"` as a later performance
    experiment after the non-autotuned import/kernel smoke passes
  - before promoting any FlashAttention instruction or explanation, validate
    import/build flags, backend selection, and at least one tracked vLLM
    scenario locally after the backend gate changes
- Promote the remaining Gemma 4 usage scenarios only after reference-host
  validation:
  - vLLM recipe-aligned reasoning, tool-calling, structured-output, and
    benchmark-lite server flows
  - use the recipe coverage worklist in
    `docs/maintainers/vllm-recipe-coverage.md` as the concrete scope for
    which Gemma 4 recipe surfaces are validated, tracked, planned, or
    advisory-only
  - add reduced probes for the interactive Gemma 4 `max_batched_8k` and
    `max_num_seqs_256` selectors only after the base feature lanes pass and the
    host memory fit is known
  - add an FP8 KV-cache smoke for Gemma 4 when the base server lane is stable,
    because the recipe lists `--kv-cache-dtype fp8` as a memory-tuning option
  - keep the E2B `kernel-probe` scenario as a tracked regression probe for the
    retired server/AsyncLLM startup fault; after the 2026-04-20 self-hosted
    rebuild, the forced Triton attention lane passes and revalidates the
    carried large-head tile-size guard
  - keep `vllm.gemma4.e2b.text.compiled` as an expected blocked compiled probe:
    with fresh cache roots on 2026-04-20 it initialized, compiled, captured
    graphs, and generated corrupted non-ASCII output instead of the expected
    five-word response
  - treat the 26B-A4B and 31B compiled text probes as compiled-capable only
    when run with fresh compile caches or after deliberate cache invalidation
  - keep the serialized `vllm.gemma4.e2b.torchao.real-model` scenario
    exploratory until language-only TorchAO serialization has repeated passes
    and an upstream path exists for fully quantized Gemma 4 multimodal towers
  - multi-image, dynamic image, audio, video, and multimodal-tool flows remain
    exploratory until each mode has its own reference-host pass; the E2B image
    server smoke now passes as the representative multimodal warmup check
  - relevant Hugging Face model-card usage patterns that are not already
    covered by the vLLM recipe scenarios
- Revisit `python-flydsl-gfx1151` once the MLIR development-surface story is
  clear.
- Benchmark whether the custom `llama.cpp` builds still justify their
  maintenance cost versus Lemonade-managed upstream runtime downloads.
- Do a ROCm-vs-Vulkan `llama.cpp` backend sweep on Strix Halo and verify
  whether Vulkan is still faster at the longer-context ranges that motivated
  the dual-backend strategy.

## Metadata And Update Story

- Make `authoritative_reference`, `advisory_references`, `divergence_notes`,
  and `update_notes` explicit across every recipe-managed package where the
  derived defaults are not strong enough.
- Audit every recipe-managed package against its best current baseline package.
- Harden the package-update story so a fresh agent can safely handle:
  - upstream source updates
  - baseline package updates
  - Blackcat Informatics recipe updates
  - new recipe entries entering the stack

## Repository Migration

- Normalize package patches so reviewable source changes live as patch files.
- Remove or ignore transient session/worklog docs once durable content has been
  extracted.
- Keep the handoff prompt current whenever a follow-up pass materially changes
  the repo structure, local-repo workflow, or benchmark plan.

## Documentation

- Keep docs under the canonical repo, not under `~/Documents`.
- Strengthen the README so it stays approachable for users while still linking
  maintainers to the deeper policy docs.
- Keep AGENTS guidance high-level and durable; avoid encoding brittle or
  easily scoutable details there.
- Review repo-local skills against current best practices and keep them focused
  on policy, architecture, and workflow rather than chat-session trivia.
- Audit every generated package-local `README.md` and `recipe.json` for update
  clarity whenever renderer policy changes.

## Local Repo User Story

- Finalize the simplest supported local pacman repo setup for Arch users.
- Document the current reference-host configuration concretely.
- Scrutinize the workflow after the first pass and reduce it to the fewest
  reasonable steps without hiding important customization points.
- Keep `amerge` and the inference-scenario tooling pleasant to use as the
  default host workflow; avoid drifting back toward one-off wrapper scripts.

## Benchmarks

- Benchmark this stack against `aur/rocm-gfx1151-bin`.
- Include a `llama.cpp` long-context sweep using the Strix Halo Home Lab wiki
  method as a reference point:
  - <https://strixhalo.wiki/AI/llamacpp-performance#long-context-length-testing>
- Use at least these model families:
  - `unsloth/gemma-4-E2B-it-GGUF:UD-Q6_K_XL`
  - `unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q4_K_XL`
  - `Qwen/Qwen3.5-0.8B` for tiny non-GGUF vLLM Qwen smoke coverage
  - `Qwen/Qwen3.6-35B-A3B-FP8` for the main non-GGUF vLLM Qwen MoE lane,
    replacing the earlier Qwen3.5 122B-A10B target in local testing plans
  - use a Qwen3.6 GGUF quantization for llama.cpp once one is chosen locally
- Capture benchmark methodology and results in repo docs before any public AUR
  publication attempt.

## Deferred Host Ergonomics

- Standardize host smoke invocations so they do not depend on interactive shell
  initialization. Prefer absolute interpreter and binary paths plus explicit
  environment setup over `PATH` mutations inherited from login-shell state.
- Decide whether some ROCm package in the local stack should add
  `/opt/rocm/bin` to interactive-shell `PATH` via `/etc/profile.d/`. Treat
  that only as host ergonomics, not as a required runtime dependency for
  scripts, services, or smoke tests.
