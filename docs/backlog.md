# Backlog

## Current Branch Closeout Gate

- Publish/install the already built `python-vllm-rocm-gfx1151` pkgrel `-27`
  and `python-amd-aiter-gfx1151` pkgrel `-8` artifacts on the reference host.
  The currently installed host still has vLLM `-26` and AITER `-7`.
- After installation, rerun the installed-host validations that should be
  stable for this branch:
  - `vllm.qwen3_5.0_8b.text.basic` should pass as the Qwen3.5 sampler-fix
    smoke
  - `vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked` should pass as
    a blocked probe asserting the non-AITER FP8 MoE backend-selection failure
  - `vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked` should pass as a
    blocked probe asserting the AITER `module_quant`/`mfma_adaptor` failure
    after AITER pkgrel `-8` is installed
- Treat Qwen3.6 FP8 MoE as a documented follow-up blocker, not a merge blocker
  for the Gemma 4 branch. The branch can close once the built artifacts are
  installed, the expected passing/blocking scenarios above are verified on the
  installed host, and the Python/package test set remains green.

## Packaging And Build Hygiene

- Resume auditing the rest of the TheRock split-package family against the
  best current CachyOS / Arch baselines.
- Convert remaining scripted source edits into durable patch files where
  practical.
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
- Revisit vLLM HIP build-path sanitization only after the gfx1151 sampler-kernel
  compile failure is understood. A trial patch that routed quoted
  `CMAKE_HIP_FLAGS` through `setup.py` (`shlex.split` on `CMAKE_ARGS`) pushed
  the prefix maps into the HIP compile lane, but both build attempts then died
  in `csrc/sampler.hip` with `Invalid dpp_ctrl value: wavefront shifts are not
  supported on GFX10+`.
- Revisit full multimodal Gemma 4 serving on the `google/gemma-4-26B-A4B-it`
  lane. The current repo-owned local vLLM repair path is intentionally
  text-only with
  `--limit-mm-per-prompt {"image":0,"audio":0,"video":0}` because leaving
  `video` implicit was enough to send vLLM back into multimodal warmup and
  reproduce the earlier GPU memory-access fault during engine initialization on
  the reference host.
- Run and validate the tracked non-eager Gemma 4 lanes separately from the
  current eager correctness lane.
  - keep the repo-owned helper defaults eager; the 2026-04-19
    `google/gemma-4-E2B-it` compiled probe is not safe enough to promote
  - the first failure surface on the installed host was torch.compile /
    Inductor code generation, because the installed Triton package still
    lacked `AttrsDescriptor.__repr__`
  - the packaging branch now renders the recipe sed patch that adds that
    `__repr__`, but the package still needs to be rebuilt and installed before
    treating the host as repaired
  - with a temporary `AttrsDescriptor.__repr__` shim, the E2B compiled +
    cudagraph path initialized but produced corrupted output; a no-cudagraph
    compiled probe then faulted the GPU during initialization/warmup
  - after the repaired Triton package was installed, the 26B-A4B offline text
    compiled probe passed with torch.compile and CUDAGraph capture, while the
    E2B compiled+cudagraph probe still generated corrupted output instead of a
    valid five-word answer
  - done for the 31B dense checkpoint: `vllm.gemma4.31b.text.compiled` passed
    on 2026-04-19 against
    `/var/cache/hf/hub/models--google--gemma-4-31B-it/snapshots/439edf5652646a0d1bd8b46bfdc1d3645761a445`
    in `360.390323` seconds with torch.compile and CUDAGraph capture
  - start from the `compiled-probe` scenarios under `inference/scenarios/`
    instead of treating the experiment as an ad hoc terminal-only rehearsal
- Reconcile Blackcat's Qwen3.5 hybrid-attention/GDN patch lane against the
  maintained `python-vllm-rocm-gfx1151` and `python-amd-aiter-gfx1151`
  package story.
  - done for the first package-carry pass: `python-vllm-rocm-gfx1151` now
    carries `0010-rocm-support-qwen35-hybrid-gdn.patch`, covering the
    still-missing AMD FLA/GDN autotune restrictions, float32 exponent
    operands, hybrid block-size realignment after ROCm platform updates, and
    hybrid full-attention fallback away from AITER attention
  - the imported GDN warmup note's `qwen3_next.py` path was stale for vLLM
    0.19.0; the maintained patch applies that guard at
    `vllm/model_executor/layers/mamba/gdn_linear_attn.py`
  - AITER-side unified attention already uses a safer
    `min(64, triton.next_power_of_2(block_size))` tile expression in the
    installed package, so no new AITER package patch is carried for that note
  - done for package-side build/test validation: unprivileged
    `tools/amerge build -y python-vllm-rocm-gfx1151` produced pkgrel `-26`,
    and the package-local vLLM test suite passed against the built `pkg/`
    tree
  - done for installed-host smoke coverage after pkgrel `-26` was installed:
    `vllm.gemma4.26b-a4b.text.basic` and
    `vllm.gemma4.26b-a4b.server.basic` both passed against
    `/bulk/hf/hub/models--google--gemma-4-26B-A4B-it/snapshots/7d4c97e54145f8ffd1a4dd1b4986a5015a517842`
    with `ROCM_AITER_UNIFIED_ATTN` and Triton unquantized MoE
- Add repo-owned validation for Qwen hybrid/GDN and MoE or shared-expert lanes
  on gfx1151.
  - done for scenario coverage: `vllm.qwen3_5.0_8b.text.basic` covers
    `Qwen/Qwen3.5-0.8B` as the tiny non-MoE Qwen3.5 hybrid/GDN smoke
  - done for scenario coverage: Qwen3.6 FP8 MoE is tracked as blocked
    kernel-probe coverage rather than a passing smoke. The current scenarios
    are `vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked` for
    non-AITER backend selection and
    `vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked` for forced AITER
    `module_quant` on gfx1151. `Qwen/Qwen3.6-35B-A3B-FP8` remains the main
    Qwen MoE/shared-expert target and replaces the earlier Qwen3.5 122B-A10B
    testing and usage target, but it is not currently a merge-blocking
    success lane for this Gemma 4 branch.
  - the old non-GGUF checkpoint blocker is cleared: the reference host's
    current `HF_HOME` is `/var/cache/hf`, with local snapshots for
    `Qwen/Qwen3.5-0.8B` and `Qwen/Qwen3.6-35B-A3B-FP8`
  - done for Qwen3.5 0.8B root-cause localization: the profile-run memory
    fault is not in GDN warmup, GDN prefill/recurrent kernels, full-attention
    kernels, decoder-layer execution, model forward, logits computation, or
    hidden-state indexing. A standalone repro faults in vLLM's Triton
    `apply_top_k_top_p` sampler filter for logits shaped `(32, 248320)` with
    top-k enabled and top-p `0.9`; the existing PyTorch fallback completes on
    the same tensor.
  - done for the package-side Qwen3.5 sampler fix: `python-vllm-rocm-gfx1151`
    now carries `0011-rocm-avoid-triton-topk-topp-sampler.patch`, which routes
    ROCm top-k/top-p filtering through vLLM's existing PyTorch fallback.
  - done for built-package validation: `tools/amerge build
    python-vllm-rocm-gfx1151` produced pkgrel `-27`, the built package payload
    contains the ROCm sampler fallback, the standalone `(32, 248320)` sampler
    repro completed through that payload, and
    `vllm.qwen3_5.0_8b.text.basic` passed against the `/var/cache/hf`
    Qwen3.5 snapshot in 42.948777 seconds. Installing/publishing pkgrel `-27`
    remains an operator step before installed-host rerun coverage.
  - Qwen3.6 FP8 MoE does not currently have a viable non-AITER fallback on
    gfx1151. With `VLLM_ROCM_USE_AITER=0` and
    `VLLM_ROCM_USE_AITER_MOE=0`, vLLM fails during backend selection with
    `No FP8 MoE backend supports the deployment configuration`; the Triton
    and batched Triton FP8 MoE gates only advertise ROCm FP8 support for
    `gfx9`, not `gfx1151`. The tracked no-AITER blocked probe passed on
    2026-04-19 in `20.962591` seconds by asserting that failure mode.
  - Qwen3.6 FP8 MoE also does not yet have a viable AITER path on gfx1151.
    The forced-AITER probe selects `Using AITER Fp8 MoE backend`, but the
    built-payload rerun with AITER pkgrel `-8` and vLLM pkgrel `-27` fails in
    AITER's `module_quant` JIT.
  - done for the AITER package-side fix: `python-amd-aiter-gfx1151` pkgrel
    `-8` keeps `hip_reduce.h` on the shipped `aiter_hip_common.h` include,
    builds through `tools/amerge build python-amd-aiter-gfx1151`, and the
    built package's installed header no longer references missing
    `hip_compat.h`
  - the built-payload Qwen3.6 rerun with AITER pkgrel `-8` and vLLM pkgrel
    `-27` cleared the earlier `hip_compat.h` blocker, selected the AITER FP8
    MoE path, and then failed during `aiter.jit.module_quant` compilation with
    `aiter_meta/csrc/include/opus/opus.hpp:3001:24: error: unknown type name
    'mfma_adaptor'`
  - done for the first AITER gfx1151 MFMA/WMMA root-cause pass: `gfx1151`
    defines `__GFX11__` and `__gfx1151__`, while AITER's `opus.hpp` defines
    `mfma_adaptor` only for `__GFX9__` device builds and chooses the
    `mfma_adaptor` path for every target except `__gfx1250__`; the alternate
    AITER `wmma_adaptor` path uses gfx1250 FP8 WMMA builtins that hipcc
    rejects for gfx1151 with a `needs target feature gfx1250-insts` error.
    Treat this as an AITER opus/gfx1151 FP8-kernel feature gap, not a small
    include or guard bug.
- Only revisit Gemma 4 on AITER fused-MoE if there is a concrete reason to
  move off the current TRITON unquantized-MoE lane.
  - treat any such attempt as a fresh experiment
  - do not restore the dropped vLLM-side AITER MoE padding carry by default
- Run and promote the newly tracked Gemma 4 usage scenarios after reference-host
  validation instead of stopping at one smoke:
  - vLLM recipe-aligned reasoning, tool-calling, structured-output, and
    benchmark-lite server flows
  - the 2026-04-19 broad non-exploratory run did not promote the E2B server
    flows: every `google/gemma-4-E2B-it` server scenario failed during
    AsyncLLM/server initialization with a ROCm GPU memory-access fault, and an
    isolated `--attention-backend TRITON_ATTN` probe reproduced the same fault
    after proving the server selected `TRITON_ATTN`
  - a representative exploratory image-input run on 2026-04-19 confirmed the
    multimodal server group is still blocked at engine initialization: vLLM
    loaded the E2B weights, began encoder-cache profiling with image items, and
    then hit the same ROCm GPU memory-access fault before any request was
    served
  - keep a dedicated follow-up for the E2B server/AsyncLLM startup fault; the
    offline eager `tools/gemma4_text_smoke.py` path for the same E2B checkpoint
    still passes, so the failure is not a model-artifact or tokenizer-path
    blocker
  - multimodal image/audio/video flows, which remain exploratory until the
    previous multimodal warmup fault is proven absent on the maintained stack
  - relevant Hugging Face model-card usage patterns that are not already
    covered by the vLLM recipe scenarios
- Immediate Gemma 4 live-validation sequence before moving to Qwen:
  - done for the first broad pass on 2026-04-19: the non-exploratory vLLM
    matrix passed 26B-A4B offline text basic plus the tiny TorchAO
    prepare/generate helper scenarios, but failed the 26B-A4B server startup
    by timeout while loading checkpoint shards and failed all E2B server flows
    with ROCm GPU memory-access faults
  - done for the first E2B eager-mode decision: do not remove eager mode for
    `google/gemma-4-E2B-it`
  - done for the first 26B-A4B offline text compiled decision after the
    repaired Triton package was installed: `vllm.gemma4.26b-a4b.text.compiled`
    passed in 350.33213 seconds with `ROCM_AITER_UNIFIED_ATTN`, `Using TRITON
    backend for Unquantized MoE`, `torch.compile took 27.34 s`, CUDAGraph
    capture, and output `These are exactly five words.`
  - done for the installed-Triton E2B compiled+cudagraph rerun:
    `vllm.gemma4.e2b.text.compiled` initialized, compiled, captured graphs,
    and generated, but failed validation with corrupted output; do not remove
    eager mode for E2B
  - done for the 31B compiled probe: `vllm.gemma4.31b.text.compiled` passed
    in `360.390323` seconds against the `/var/cache/hf` snapshot for
    `google/gemma-4-31B-it`
  - next keep the new E2B `kernel-probe` scenario around as a tracked
    regression probe for the server fault, because the forced Triton attention
    lane still faults and therefore rules out an AITER-only explanation
  - done for 26B-A4B MoE backend probes: automatic/default MoE and forced
    `--moe-backend triton` both passed the server smoke with
    `Using TRITON backend for Unquantized MoE`; forced
    `--moe-backend aiter` failed fast with
    `ValueError: ROCm AITer MoE backend is not available for this configuration`
  - done for TorchAO warning triage: the TorchAO config-version warning is
    expected with the required version-2 int8 weight-only config on TorchAO
    0.17.0, and the ROCm custom paged-attention fallback warning is a vLLM
    shape/config selector warning that did not appear in the Gemma 4 E2B
    online TorchAO run
  - done for real-model TorchAO viability: the tracked
    `vllm.gemma4.e2b.torchao.online-real-model` scenario passed on 2026-04-19
    with `quantization=torchao`, `ROCM_AITER_UNIFIED_ATTN`, and `generation_ok`
  - next keep the serialized
    `vllm.gemma4.e2b.torchao.real-model` scenario exploratory until the
    TorchAO/vLLM metadata mismatch is fixed; it now writes processor files but
    still fails during weight loading with
    `AttributeError: 'Tensor' object has no attribute 'tensor_data_names'`
  - done for representative multimodal probing:
    `vllm.gemma4.e2b.server.image` failed before request serving during
    encoder-cache image profiling with the same ROCm GPU memory-access fault;
    leave the remaining multimodal scenarios exploratory and blocked behind
    the shared E2B server/AsyncLLM startup fault
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
  - Paudley recipe updates
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
  - done for the first unprivileged package-build pass: `amerge build` no
    longer starts sudo keepalive for build-only plans, and `amerge history`
    can inspect retained plan state without write access to plan directories

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
