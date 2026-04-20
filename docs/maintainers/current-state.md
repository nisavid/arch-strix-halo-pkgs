# Current State

Status as of 2026-04-19.

## Live Host State

The first full live cutover completed successfully on the reference Arch host.

The reference host's active Hugging Face cache for current validation work is
`/var/cache/hf`, not the older `/bulk/hf` cache. Current local non-GGUF model
snapshots relevant to this branch are:

- `google/gemma-4-31B-it` at
  `/var/cache/hf/hub/models--google--gemma-4-31B-it/snapshots/439edf5652646a0d1bd8b46bfdc1d3645761a445`
- `Qwen/Qwen3.5-0.8B` at
  `/var/cache/hf/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17`
- `Qwen/Qwen3.6-35B-A3B-FP8` at
  `/var/cache/hf/hub/models--Qwen--Qwen3.6-35B-A3B-FP8/snapshots/61a5771f218894aaacf97551e24a25b866750fc2`

Use `Qwen/Qwen3.6-35B-A3B-FP8` as the main Qwen MoE/shared-expert target for
this dev arc; it replaces the earlier Qwen3.5 122B-A10B testing and usage
target. Its local config advertises `Qwen3_5MoeForConditionalGeneration` /
`qwen3_5_moe`, so the maintained Qwen3.5/GDN package carry is still relevant
to this lane.

Installed and validated at least once on the live host:

- generated TheRock/ROCm split package family
- AOCL layer
- optimized `python-gfx1151`
- rebuilt wheel layer
- Triton and AOTriton
- PyTorch, TorchVision, AITER, and vLLM
- `llama.cpp` HIP and Vulkan backends
- Lemonade server/app/meta packages

## Live Smoke Coverage

The following smoke checks have already passed on the reference host:

- `rocminfo`
- `hipcc --version`
- `amdclang --version`
- `python -c 'import torch; ...'`
- `python -c 'import vllm; ...'`
- `python -c 'import amdsmi; ...'`
- `llama-cli-hip-gfx1151 --help`
- `llama-cli-vulkan-gfx1151 --help`
- `lemonade --help`
- `lemond --help`
- `google/gemma-4-E2B-it` offline vLLM smoke on ROCm with text-only multimodal
  limits and recipe-style chat-template prompting
- `google/gemma-4-31B-it` offline vLLM smoke on ROCm with text-only multimodal
  limits and recipe-style chat-template prompting
- `google/gemma-4-E2B-it` offline eager vLLM smoke on 2026-04-19 with
  `tools/gemma4_text_smoke.py`, `--max-model-len 128`, and text-only
  multimodal limits; the same checkpoint's server/AsyncLLM path currently
  fails separately during initialization

## Important Package Decisions

- `python-gfx1151` is rebased onto Arch/Cachy Python `3.14.4`, not the
  recipe's older Python `3.13.x` pin.
- `amdsmi-gfx1151` now installs an `amd_smi.pth` import hook into Python
  `site-packages`, so Python `3.14` can import the ROCm-shipped `amdsmi`
  module from `/opt/rocm/share/amd_smi` without extra `PYTHONPATH` glue on the
  host.
- `rocm-core-gfx1151` now uses CachyOS `rocm-core` as its distro-integration
  baseline while still shipping the newer TheRock 7.13 core payload. The
  rebuilt split package now carries the expected `ld.so`/shell integration
  files, `rdhc` wrapper/docs, and license copies; the remaining file-list
  delta against Cachy is limited to intentional TheRock-owned additions such
  as `nlohmann`, `.hipInfo`, `share/modulefiles`, and `share/therock`, plus
  the expected versioned `rocmCoreTargets` / `librocm-core.so` filenames.
- `python-pytorch-opt-rocm-gfx1151` tracks `ROCm/pytorch` `release/2.11`,
  pinned to commit `0446f7ba2fd`, with package version aligned to the built
  wheel version.
- `python-pytorch-opt-rocm-gfx1151` now also pins its BLAS/LAPACK provider to
  `openblas` and assembles the wheel in two stages on Arch Python `3.14`:
  build the CMake artifacts first, tolerate the known
  `_sysconfigdata__linux_x86_64-linux-gnu.cpython-314.pyc` install failure,
  restage the built `torch/lib` and `torch/bin` payloads, then run
  `SKIP_BUILD_DEPS=1 python setup.py bdist_wheel`. That avoids two host-side
  regressions observed on this lane:
  - oneMKL auto-detection contaminating the wheel with `/opt/intel/oneapi`
    runpaths
  - the raw install target mirroring `/usr/lib` and `/usr/include` into the
    source tree and poisoning the staged wheel with host packages
- `python-numpy-gfx1151` now also pins NumPy's Meson BLAS/LAPACK selection to
  `openblas`. Do not let the wheel build auto-detect oneMKL just because
  `intel-oneapi-mkl` is installed on the build host; that produced a broken
  wheel with `/opt/intel/oneapi` runpaths and `undefined symbol:
  mkl_blas_dgemm` at import time.
- `python-torchvision-rocm-gfx1151` now rebuilds cleanly against the paired
  PyTorch lane without the earlier build-only `librocsolver.so.0` shim; if
  that workaround ever becomes necessary again, treat it as a PyTorch/runtime
  regression rather than reintroducing the shim in TorchVision.
- `python-torchvision-rocm-gfx1151` also now sanitizes embedded HIP source
  paths correctly: the rebuilt `_C.so` no longer leaks repo-local `$srcdir`
  paths and instead points at `/usr/src/debug/python-torchvision-rocm-gfx1151`.
- `python-openai-harmony-gfx1151` is now the local closure package for vLLM's
  GPT-OSS/Harmony path, using `aur/python-openai-harmony` as the baseline but
  carrying upstream's missing `python-pydantic` runtime dependency.
- `python-mistral-common-gfx1151` is now the local closure package for the
  Gemma 4 / Transformers `5.5.x` processor path because the older host
  `python-mistral-common 1.8.6-1` package did not export
  `mistral_common.protocol.instruct.request.ReasoningEffort`.
- `python-sentencepiece-gfx1151` already carries the bundled-build patch needed
  to avoid host `sentencepiece` shared-library ABI drift, and the current
  built package artifact under `packages/python-sentencepiece-gfx1151/pkg/`
  is self-contained at the ELF level.
- `python-transformers-gfx1151` is now the local closure package for Gemma 4
  support on this stack because the host `python-transformers 5.2.0-1` lane
  did not ship `transformers.models.gemma4`; the repo currently tracks PyPI
  `transformers 5.5.4`, which is the first verified published lane to include
  that module.
- `python-vllm-rocm-gfx1151` uses upstream `v0.19.0` tarball plus the local
  Python-3.14 compatibility delta and now depends on the local
  `python-openai-harmony-gfx1151`, `python-transformers-gfx1151`, and
  `python-mistral-common-gfx1151` packages for Harmony and Gemma-4-capable
  runtime closure.
- `python-amd-aiter-gfx1151` now carries an installed-system JIT runtime fix
  so the compiled HIP helper module can be imported from the user JIT cache
  under `~/.aiter/jit/` without requiring a manually exported `AITER_JIT_DIR`.
  The same patch also teaches the runtime to find `hipcc` via
  `/opt/rocm/bin/hipcc` and the standard ROCm env vars instead of relying on
  interactive-shell `PATH` setup.
- The earlier host Gemma 4 tokenizer failure was not a repo-package design
  gap; it was live-system drift. The host had
  `python-sentencepiece-gfx1151 0.2.1.r8.d20260317.gad42886-1` installed, and
  that older installed extension still linked against stale host
  `sentencepiece` / `protobuf` / `abseil` shared libraries. The rebuilt local
  package lane is now the validated reference state.
- `python-vllm-rocm-gfx1151` also carries a ROCm-specific compatibility gate
  for the vendored `triton_kernels` tree, so the `gfx1151` lane falls back
  cleanly when the installed Triton runtime lacks CUDA-only APIs such as
  `triton.language.target_info`.
- `python-vllm-rocm-gfx1151` also now carries two small host-facing runtime
  compatibility fixes:
  - the ROCm GCN-arch fallback no longer crashes in an import-time
    `warning_once` circular path when `amdsmi` cannot return ASIC info and
    vLLM falls back to `torch.cuda`
  - SageMaker-specific API routers now treat
    `model_hosting_container_standards` as optional, so base CLI and API usage
    no longer hard-fail on that extra package being absent
- The old external `python-torchao-rocm 0.16.0-1` package on the reference
  host failed to load its optional `_C.abi3.so` extension because the shipped
  binary was not import-clean against the installed PyTorch runtime: it
  is missing a usable `torch/lib` runpath and still fails on unresolved
  `at::TensorBase::const_data_ptr` symbols once the torch shared libraries are
  made visible. Generic vLLM startup is now clean on non-TorchAO code paths:
  plain `vllm --help` no longer surfaces the warning after the local
  lazy-import boundaries on the version path, quantization registry, benchmark
  CLI, OpenAI protocol, engine arg utils, and top-level help registration.
  The remaining warning on the old text-only Gemma smoke was traced instead to
  the smoke harness importing `transformers.AutoProcessor`, which reaches
  `transformers.quantizers.quantizer_torchao`; `AutoTokenizer` is clean on the
  same host. The TorchAO Python-level APIs vLLM actually touches
  (`config_from_dict`, `quantize_`, and packed-tensor conversion) still work
  on the reference host. This repo now also carries a local
  `python-torchao-rocm-gfx1151` `0.17.0` lane aligned to torch `2.11.0+`, with
  `VERSION_SUFFIX=` to avoid TorchAO's `+git` compatibility bypass,
  `ROCM_HOME=/opt/rocm` so PyTorch's extension helper uses the real
  split-layout ROCm headers instead of falling back to `/usr`, a local ROCm
  arch patch so source builds honor `PYTORCH_ROCM_ARCH=gfx1151`, and a
  post-install RPATH fix so the shipped `_C` extension can resolve
  `torch/lib`. The staged package now builds locally, shows
  `RUNPATH [$ORIGIN:$ORIGIN/../torch/lib:/opt/rocm/lib]`, resolves cleanly
  under `ldd -r` against the current torch/ROCm stack, imports cleanly from
  the staged payload, and is now the installed validated host lane.
- The current Gemma 4 / vLLM smoke story is now split cleanly:
  - the earlier ROCm runtime blocker was real and is now fixed on the host:
    vLLM selects `ROCM_AITER_UNIFIED_ATTN`, and AITER imports its compiled JIT
    helper from `~/.aiter/jit/module_aiter_core.so`
  - the remaining "empty output" result came from using base Gemma 4
    checkpoints (`google/gemma-4-E2B`, `google/gemma-4-31B`) for
    assistant-style chat smokes rather than the instruction-tuned `-it`
    checkpoints recommended by the official vLLM Gemma 4 recipe
  - a host debug run against base `google/gemma-4-E2B` showed the stack is
    capable of real generation on Strix Halo: plain completion prompts emit
    tokens, but assistant/chat-style prompts degrade into prompt echo, EOS,
    and whitespace rather than useful assistant responses
- The official vLLM Gemma 4 recipe adds several workflow rules that apply to
  this repo's local ROCm lane even though its AMD deployment examples target
  MI300X/MI325X/MI350X/MI355X and Docker:
  - use instruction-tuned `google/gemma-4-*-it` checkpoints for assistant,
    chat, reasoning, tool-calling, and OpenAI-compatible server smokes
  - for text-only offline inference, render prompts with
    `tokenizer.apply_chat_template(..., add_generation_prompt=True)` before
    calling `LLM.generate()`
  - for multimodal offline inference, use `AutoProcessor.apply_chat_template`
    and pass multimodal payloads explicitly via `multi_modal_data`
  - for text-only workloads, set
    `--limit-mm-per-prompt {"image":0,"audio":0,"video":0}` to
    skip unnecessary multimodal profiling and encoder reservations
  - for image-only workloads, set `--limit-mm-per-prompt {"audio":0}`
  - for throughput-oriented serving, `--async-scheduling` is recommended
  - for benchmark runs, disable prefix caching with
    `--no-enable-prefix-caching` to get more consistent measurements
  - for Gemma 4 thinking/tool-calling server flows, pair
    `--reasoning-parser gemma4`, `--tool-call-parser gemma4`,
    `--enable-auto-tool-choice`, and an appropriate Gemma 4 chat template
  - prefer a model-bundled `chat_template.jinja` when the checkpoint ships
    one; `tools/gemma4_server_smoke.py` now auto-resolves that first for
    `--mode tool`
- The current validated Gemma 4 local smoke workflow on Strix Halo is:
  - use `google/gemma-4-E2B-it` or `google/gemma-4-31B-it`
  - render the prompt with the checkpoint's tokenizer chat template for
    text-only smokes; the tracked tool is `tools/gemma4_text_smoke.py`
  - reserve `AutoProcessor.apply_chat_template` for multimodal Gemma 4 smokes
  - run vLLM in text-only mode with
    `limit_mm_per_prompt={"image": 0, "audio": 0, "video": 0}`
  - keep `enforce_eager=True` for the current local smoke path
  - expect the 31B instruction-tuned checkpoint to emit an empty thought block
    prefix when thinking is disabled, matching the upstream Gemma 4 model card
- The `google/gemma-4-26B-A4B-it` local ROCm lane is now validated for the
  repo-owned basic text/basic-server workflow:
  - the 2026-04-17 reference-host run of the current tracked lane completed
    successfully for both
    `vllm.gemma4.26b-a4b.text.basic` and
    `vllm.gemma4.26b-a4b.server.basic`
  - the current validated shape is still the constrained text-only lane:
    `--limit-mm-per-prompt {"image":0,"audio":0,"video":0}`,
    `--max-model-len 128`, `--max-num-batched-tokens 32`, and
    `--gpu-memory-utilization 0.75`
  - the passing host logs show the split that matters:
    `ROCM_AITER_UNIFIED_ATTN` for attention, successful import of AITER's JIT
    helper from `~/.aiter/jit/module_aiter_core.so`, and
    `Using TRITON backend for Unquantized MoE`
  - the tracked outputs on that passing lane are now concrete:
    `tools/gemma4_text_smoke.py` returned `These are exactly five words.`, and
    `tools/gemma4_server_smoke.py --mode basic` returned
    `Deep blue waves crash endlessly.`
  - the repo-owned basic text/server helpers still default to
    `enforce_eager=True` / `--enforce-eager` as a conservative
    correctness/isolation choice. The separate tracked
    `vllm.gemma4.26b-a4b.text.compiled` probe now validates that the 26B-A4B
    offline text path can run with torch.compile and CUDAGraph after the
    Triton `AttrsDescriptor.__repr__` repair
  - `tools/gemma4_server_smoke.py` now uses a `420`-second startup budget for
    this lane because cold `google/gemma-4-26B-A4B-it` server loads on the
    reference host can exceed both the earlier `180`-second default and a
    `300`-second budget when checkpoint loading is slow
  - the 2026-04-19 MoE backend probes keep the maintained MoE lane on
    Triton: the automatic/default server probe and the forced
    `--moe-backend triton` probe both passed with
    `Using TRITON backend for Unquantized MoE`; the forced
    `--moe-backend aiter` probe failed during model construction with
    `ValueError: ROCm AITer MoE backend is not available for this configuration`
  - `tools/gemma4_server_smoke.py` now launches vLLM in its own process group
    and tears down that whole group on exit; an older helper revision could
    leave an orphaned `VLLM::EngineCore` holding roughly `89 GiB` of VRAM
    after an otherwise successful basic-server smoke
  - the reusable host-side validation path is now split cleanly:
    - rebuild and reinstall with `tools/amerge`
    - run tracked validations with `tools/run_inference_scenarios.py`
  - `tools/run_inference_scenarios.py` now logs `amd-smi process -G --json`
    before and after `vllm` scenarios when available, and fails a `vllm`
    scenario early if a preexisting stale `VLLM::EngineCore` is already
    squatting on VRAM, so the failure mode is explicit instead of surfacing
    later as a generic `gpu_memory_utilization` startup error
  - leaving `video` implicit in `--limit-mm-per-prompt` is still enough to
    send vLLM back into multimodal warmup on this host and reproduce the older
    GPU memory-access fault during engine initialization
  - the questioned carries are now split cleanly by evidence:
    - keep
      `python-amd-aiter-gfx1151/0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch`
      because the earlier forced AITER fused-MoE lane directly reproduced a
      `ksplit=0` fault, and current upstream AITER still lacks the full
      no-split normalization plus stage-2 `splitk` forwarding
    - keep the split RDNA header carries:
      `python-amd-aiter-gfx1151/0001-gfx1151-rdna35-header-compat.patch`
      for the `vec_convert.h` gfx11 packed-op fallbacks, and
      `python-amd-aiter-gfx1151/0006-rdna35-hip-reduce-wave32-dpp-compat.patch`
      for the broader `hip_reduce.h` wave32/DPP rewrite
    - keep
      `python-vllm-rocm-gfx1151/0007-rocm-enable-gfx1x-aiter-and-prefer-it-for-gemma4.patch`
      because the validated lane still depends on the gfx1x AITER support plus
      the Gemma 4 `ROCM_AITER_UNIFIED_ATTN` override
    - keep the broader fused-MoE default-policy carry dropped: the
      2026-04-17 reference-host rerun faulted the GPU as soon as that policy
      forced the AITER CK 2-stage fused-MoE path without an explicit runtime
      override
    - drop the earlier
      `python-vllm-rocm-gfx1151/0010-rocm-pad-gemma4-moe-intermediate-for-aiter.patch`
      carry from the maintained package story: once the fused-MoE default
      policy was gone, the passing host lane no longer exercised AITER MoE at
      all, so the padding fix was a dormant carry rather than part of the
      validated default
  - the repo keeps a reproducible two-step handoff for this lane:
    - `tools/amerge run python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151`
    - `python tools/run_inference_scenarios.py --scenario vllm.gemma4.26b-a4b.text.basic --scenario vllm.gemma4.26b-a4b.server.basic --model-path google/gemma-4-26B-A4B-it=/absolute/path/to/google/gemma-4-26B-A4B-it`
    - logs land under ignored `docs/worklog/amerge/<plan-id>/`
      and `docs/worklog/inference-runs/<timestamp>/` directories so the
      follow-up loop does not depend on copy-pasted terminal output
- The tracked Gemma 4 / vLLM scenario matrix now includes the usage surfaces
  from the official vLLM Gemma 4 recipe:
  - basic chat, reasoning, tool calling, tool calling with thinking,
    structured output, structured output with thinking, benchmark-lite, and a
    full-feature text-only server smoke for `google/gemma-4-E2B-it`
  - multimodal image, multi-image, dynamic-resolution image, audio, video, and
    multimodal-tool server smokes for `google/gemma-4-E2B-it`
  - compiled-path probes for `google/gemma-4-E2B-it`,
    `google/gemma-4-31B-it`, and `google/gemma-4-26B-A4B-it`
  - forced Triton, automatic, and forced AITER MoE backend probes for
    `google/gemma-4-26B-A4B-it`
  - tiny and real-model TorchAO probes
- Scenario selection now treats `tags = ["exploratory"]` as opt-in for broad
  selections. `python tools/run_inference_scenarios.py --engine vllm` skips
  the exploratory multimodal, compiled-path, forced-kernel, and real-model
  TorchAO probes by default; use `--include-exploratory` with any broad or
  `--tag` selector, or use explicit `--scenario` selectors, when deliberately
  running those investigations.
- The newly tracked recipe, compiled, MoE-backend, multimodal, and real-model
  TorchAO scenarios are not all new validated defaults yet. Promote any
  remaining exploratory lane only after a reference-host run records the exact
  model binding, backend split, warning surface, and logs under
  `docs/worklog/inference-runs/`.
- The next Gemma 4 live-validation order is intentionally staged:
  non-exploratory broad `vllm` scenarios first, then `compiled-probe`
  scenarios to answer the eager-mode question, MoE backend probes after that,
  and finally real-model TorchAO plus multimodal exploratory scenarios. The
  first compiled, MoE, TorchAO, and representative multimodal decisions are
  now recorded; keep the remaining multimodal scenarios exploratory until the
  shared E2B server/AsyncLLM warmup fault is fixed.
- The 2026-04-19 Gemma 4 broad vLLM pass is recorded but not promotable as a
  default server matrix:
  - passed:
    `vllm.gemma4.26b-a4b.text.basic`,
    `vllm.torchao.tiny.prepare`, and `vllm.torchao.tiny.generate`
  - `vllm.gemma4.26b-a4b.text.basic` produced
    `These are exactly five words.` and selected
    `ROCM_AITER_UNIFIED_ATTN` plus `Using TRITON backend for Unquantized MoE`
  - `vllm.gemma4.26b-a4b.server.basic` timed out after the helper's
    300-second startup budget while still loading safetensors checkpoint
    shards; no stale `VLLM::EngineCore` process remained afterward
  - the helper startup budget was then raised to 420 seconds, and the later
    26B-A4B MoE server probes reached readiness and completed within that
    budget
  - every non-exploratory `google/gemma-4-E2B-it` server scenario failed
    during server/AsyncLLM initialization with a ROCm GPU memory-access fault
  - an isolated E2B server basic rerun reproduced the same fault, while a
    direct offline eager E2B text smoke passed and returned
    `The quick brown fox jumps.`
  - an explicit `--attention-backend TRITON_ATTN` E2B server probe proved vLLM
    selected `Using TRITON_ATTN backend` and still hit the same GPU
    memory-access fault, so the E2B server fault is not explained by AITER
    unified attention alone
  - a representative exploratory multimodal probe,
    `vllm.gemma4.e2b.server.image`, failed on 2026-04-19 before any image
    request was sent: the server selected `ROCM_AITER_UNIFIED_ATTN`, loaded
    weights, initialized the encoder cache with an image budget, profiled 29
    maximum-size image items, and then hit the same ROCm GPU memory-access
    fault during engine initialization
- The 2026-04-19 compiled-path investigation keeps eager mode as the supported
  Gemma 4 helper default for E2B, but no longer for every Gemma 4 checkpoint:
  - the pre-repair host Triton package lacked
    `AttrsDescriptor.__repr__`, causing torch.compile / Inductor generated
    Python to contain an invalid angle-bracket object repr and fail with
    `SyntaxError`
  - this branch fixed the package renderer so the recipe's Triton sed patch is
    present in `packages/python-triton-gfx1151/PKGBUILD`; after rebuilding and
    installing `python-triton-gfx1151`, the normal compiled probes no longer
    need a temporary runtime shim
  - `makepkg -C -o --noconfirm` now validates the generated PKGBUILD's
    prepare-time patch application and the prepared source contains
    `AttrsDescriptor.__repr__`; the full `tools/amerge run
    python-triton-gfx1151` publish/install path still requires operator sudo
  - after the repaired Triton package was installed,
    `vllm.gemma4.26b-a4b.text.compiled` passed on the reference host in
    `350.33213` seconds with `enforce_eager=False`,
    `ROCM_AITER_UNIFIED_ATTN`, `Using TRITON backend for Unquantized MoE`,
    torch.compile, and CUDAGraph capture; the output was
    `These are exactly five words.`
  - the same run showed `torch.compile took 27.34 s in total`, graph capture
    completed, and the model generated the expected basic smoke output, so the
    26B-A4B offline text lane can be treated as compiled-capable after the
    Triton `AttrsDescriptor.__repr__` repair
  - after the repaired Triton package was installed,
    `vllm.gemma4.e2b.text.compiled` no longer failed with the old SyntaxError:
    it initialized, compiled, captured graphs, and generated, but the output
    was corrupted (`docked calcS ...`) and failed the basic smoke assertion
  - with a temporary `AttrsDescriptor.__repr__` shim, the E2B compiled +
    cudagraph path got through `torch.compile` and CUDAGraph capture but
    generated corrupted text, so it is not promotable
  - with the same shim and CUDAGraph disabled, the E2B compiled path faulted
    the GPU during initialization/warmup
  - do not remove eager mode for `google/gemma-4-E2B-it`; the
    E2B compiled path still generates invalid text after the Triton repair
  - `vllm.gemma4.31b.text.compiled` passed on 2026-04-19 against
    `/var/cache/hf/hub/models--google--gemma-4-31B-it/snapshots/439edf5652646a0d1bd8b46bfdc1d3645761a445`
    in `360.390323` seconds, so the dense 31B instruction-tuned checkpoint is
    compiled-capable on the current installed Triton/vLLM stack
- The 2026-04-19 26B-A4B MoE backend investigation confirms that the current
  package should stay on Triton for sparse MoE execution:
  - `vllm.gemma4.26b-a4b.server.moe-auto` passed in `288.508121` seconds with
    the default backend selection, `ROCM_AITER_UNIFIED_ATTN`, and
    `Using TRITON backend for Unquantized MoE`
  - `vllm.gemma4.26b-a4b.server.moe-triton` passed in `344.765496` seconds
    with explicit `--moe-backend triton`, `ROCM_AITER_UNIFIED_ATTN`, and
    `Using TRITON backend for Unquantized MoE`
  - `vllm.gemma4.26b-a4b.server.moe-aiter` failed in `24.091119` seconds
    before weight loading with
    `ValueError: ROCm AITer MoE backend is not available for this configuration`
  - do not restore the broader fused-MoE default-policy carry or the dormant
    Gemma 4 AITER MoE padding carry on the basis of the current evidence
- The first Qwen3.5 hybrid-attention/GDN package-carry reconciliation is now
  represented in `python-vllm-rocm-gfx1151`.
  - `0010-rocm-support-qwen35-hybrid-gdn.patch` carries the missing vLLM-side
    pieces from Blackcat Informatics' advisory lane: AMD-restricted FLA
    autotune grids, float32 GDN exponent operands, GDN warmup at `T=64`, hybrid
    block-size realignment after ROCm platform updates, and hybrid
    full-attention fallback away from AITER attention
  - the imported warmup note's `qwen3_next.py` path is stale for vLLM 0.19.0;
    the maintained patch applies the guard in
    `vllm/model_executor/layers/mamba/gdn_linear_attn.py`
  - no new `python-amd-aiter-gfx1151` patch is currently carried for the
    advisory unified-attention tile note because the installed AITER source
    already uses a safer `min(64, triton.next_power_of_2(block_size))` tile
    expression
  - unprivileged `tools/amerge build -y python-vllm-rocm-gfx1151` completed
    for pkgrel `0.19.0.r8.d20260317.gad42886-26`, producing
    `python-vllm-rocm-gfx1151-0.19.0.r8.d20260317.gad42886-26-x86_64.pkg.tar.zst`;
    `pytest packages/python-vllm-rocm-gfx1151/tests -q` then passed against
    the freshly populated `pkg/` tree
  - after pkgrel `-26` was installed, the existing Gemma 4 26B-A4B
    installed-host lane still passed with the package:
    `vllm.gemma4.26b-a4b.text.basic` passed in `195.710255` seconds, and
    `vllm.gemma4.26b-a4b.server.basic` passed in `309.115382` seconds against
    `/bulk/hf/hub/models--google--gemma-4-26B-A4B-it/snapshots/7d4c97e54145f8ffd1a4dd1b4986a5015a517842`;
    the logs selected `ROCM_AITER_UNIFIED_ATTN`, imported AITER's JIT helper,
    used `Using TRITON backend for Unquantized MoE`, and ended with no
    running GPU processes detected
  - the old non-GGUF checkpoint blocker is cleared by the `/var/cache/hf`
    cache move: use `Qwen/Qwen3.5-0.8B` for tiny Qwen3.5 hybrid/GDN smoke
    coverage and `Qwen/Qwen3.6-35B-A3B-FP8` for the main Qwen
    MoE/shared-expert lane
  - tracked Qwen scenarios now exist:
    `vllm.qwen3_5.0_8b.text.basic` for the tiny hybrid/GDN smoke and
    `vllm.qwen3_6.35b-a3b-fp8.text.basic` for the Qwen3.6 FP8 MoE smoke
  - `vllm.qwen3_5.0_8b.text.basic` failed on 2026-04-19 after model loading
    with a ROCm GPU memory-access fault. The failure still reproduced with
    `FLA_GDN_FIX_BT=1`, with `--max-num-batched-tokens 32`, with forced
    `TRITON_ATTN`, and after skipping
    `GatedDeltaNetAttention._warmup_prefill_kernels`, so the remaining blocker
    is deeper than the known `T < 64` GDN warmup/autotune issue.
  - `vllm.qwen3_6.35b-a3b-fp8.text.basic` defaults to the AITER FP8 MoE path
    through `VLLM_ROCM_USE_AITER=1` and `VLLM_ROCM_USE_AITER_MOE=1`. On the
    currently installed AITER pkgrel `-7`, the 2026-04-19 run selected
    `Using AITER Fp8 MoE backend`, loaded all 42 checkpoint shards, and then
    failed during `module_quant` JIT compilation because installed
    `hip_reduce.h` included nonexistent `hip_compat.h`.
  - `python-amd-aiter-gfx1151` pkgrel `-8` is the package-side fix for that
    Qwen3.6 blocker: `0006-rdna35-hip-reduce-wave32-dpp-compat.patch` keeps
    the shipped `aiter_hip_common.h` include, the package-local tests pass,
    `tools/amerge build python-amd-aiter-gfx1151` completed, and the built
    package's `aiter_meta/csrc/include/hip_reduce.h` no longer references
    `hip_compat.h`. Publishing/installing pkgrel `-8` still needs operator
    sudo; `tools/amerge publish python-amd-aiter-gfx1151` could not run
    autonomously because sudo requested an interactive password.
- The tracked host-side follow-up helper for OpenAI-compatible server smokes is
  now `tools/gemma4_server_smoke.py`.
  - `--mode basic` launches
    `python -m vllm.entrypoints.openai.api_server` from the active interpreter
    and sends a plain `/v1/chat/completions` request, so the smoke does not
    depend on interactive-shell `PATH` setup
  - for the current `google/gemma-4-26B-A4B-it` validation lane, the helper
    now
    defaults `--max-model-len` to `128`,
    `--max-num-batched-tokens` to `32`, and
    `--limit-mm-per-prompt` to `{"image":0,"audio":0,"video":0}` so the
    repo-owned smoke stays on the intended text-only path
  - `--mode reasoning` adds `--reasoning-parser gemma4` and sends
    `chat_template_kwargs={"enable_thinking": true}` plus
    `skip_special_tokens=false` in the OpenAI-compatible request body
  - the helper now defaults `--max-model-len` to `1024` for `reasoning` and
    `tool` modes; the earlier `512`-token default was enough for plain chat
    but truncated Gemma 4 reasoning before the parser could finish
  - `--mode tool` adds `--tool-call-parser gemma4`,
    `--reasoning-parser gemma4`, `--enable-auto-tool-choice`, and a Gemma 4
    chat template resolved from the local checkpoint when available or
    otherwise required explicitly via `--chat-template`, then validates both
    the initial tool call and the follow-up tool response round trip
- An earlier reference-host pass verified three OpenAI-compatible Gemma 4
  server flows with `google/gemma-4-E2B-it`, but the 2026-04-19 broad matrix
  currently reproduces a server/AsyncLLM GPU memory-access fault before those
  flows can be promoted as maintained defaults:
  - basic chat completion passed with the helper's default `--max-model-len 512`
  - reasoning parsing passed with `--mode reasoning`, `--reasoning-parser gemma4`,
    `skip_special_tokens=false`, and `--max-model-len 1024`; the returned
    OpenAI message now splits cleanly into `message.reasoning` and
    `message.content`
  - tool-calling passed with `--mode tool`, `--reasoning-parser gemma4`,
    `--tool-call-parser gemma4`, `--enable-auto-tool-choice`, and a compatible
    Gemma 4 chat template; the first response returns a `get_weather` tool
    call and the follow-up tool response round trip returns a normal assistant
    answer
- The tracked TorchAO-dependent validation tool is now
  `tools/torchao_vllm_smoke.py`.
  - `--prepare-only` builds a tiny local Llama checkpoint, reloads it through
    `transformers.TorchAoConfig(Int8WeightOnlyConfig(version=2))`, and saves a
    TorchAO-serialized safetensors checkpoint without needing a tokenizer or
    network download.
  - the full mode has now passed on the reference host: it first runs a raw
    GPU `copy_` probe that mirrors vLLM's TorchAO weight-loading contract, then
    loads the same local checkpoint through vLLM with `skip_tokenizer_init=True`
    and generates from raw `prompt_token_ids`, which exercises the serialized
    TorchAO path rather than the BF16 Gemma path.
  - keep the helper checkpoint in bfloat16. The first failing helper variant
    serialized TorchAO weights with `dtype=torch.float32`, while vLLM's
    destination tensors were created with `dtype=torch.bfloat16`; TorchAO
    treats that dtype as part of tensor metadata and rejects `copy_` before
    vLLM reaches model init.
  - the helper now also has a real-model path:
    `--source-model <model-id-or-path>` quantizes with
    `TorchAoConfig(Int8WeightOnlyConfig(version=2))`, saves the processor or
    tokenizer files, and runs a tokenizer-backed vLLM generation pass; use
    `--dry-run` first to inspect the chosen quantized output directory and
    execution mode.
  - the helper also supports `--online-quantization` with `--source-model`;
    that path serves the source model directly and passes the same TorchAO
    int8 weight-only config through vLLM `hf_overrides`, so it avoids writing a
    serialized quantized checkpoint.
  - the helper can classify the two known warning markers on TorchAO/vLLM
    paths, but the currently committed classifier is only a support surface;
    live warning conclusions still need to come from a real host run log.
- `llama.cpp-hip-gfx1151` uses `aur/llama.cpp-hip` as the authoritative
  baseline reference.
- `llama.cpp-vulkan-gfx1151` currently uses `aur/llama.cpp-vulkan-bin` as the
  closest backend-specific reference until a maintained source-build Vulkan
  package exists.
- Lemonade is intentionally customized so:
  - `llamacpp:rocm` and `llamacpp:vulkan` are packaged system-managed backends
  - `llamacpp:cpu` remains Lemonade-managed and downloadable
  - `llamacpp:system` is removed from this custom variant
  - the backend table identifies the packaged backends explicitly as:
    - `System llama-server-hip-gfx1151 llama.cpp b8611`
    - `System llama-server-vulkan-gfx1151 llama.cpp b8611`

## Known Deferred Follow-up Work

- `python-flydsl-gfx1151`
  - blocked on the current `rocm-llvm-gfx1151` MLIR development surface being
    insufficient for downstream FlyDSL packaging
- package hygiene
  - remove remaining embedded build-path leakage where still present in
    PyTorch and vLLM
  - convert remaining scripted source edits into durable patch files where
    practical
- vLLM build-path follow-up
  - a trial patch that taught `setup.py` to `shlex.split()` quoted
    `CMAKE_ARGS` and injected `CMAKE_HIP_FLAGS` did route source-prefix maps
    into the HIP compile lane, but it also made both vLLM build attempts fail
    in `csrc/sampler.hip` on gfx1151 with:
    `Invalid dpp_ctrl value: wavefront shifts are not supported on GFX10+`
  - treat that as the current blocker before attempting any further vLLM
    build-path sanitization
- vLLM/TorchAO follow-up
  - the reference host is now on the local
    `python-torchao-rocm-gfx1151 0.17.0` package, and `import torchao` is
    warning-free aside from an upstream Python `SyntaxWarning` in
    `torchao/quantization/quant_api.py`
  - the first real TorchAO-dependent validation path has now passed on the
    reference host via `tools/torchao_vllm_smoke.py`, including the raw GPU
    `copy_` probe and the vLLM `quantization="torchao"` load/generate path
  - warning investigation completed on 2026-04-19:
    `Stored version is not the same as current default version` comes from
    TorchAO config deserialization with stored version 2 while the current
    `Int8WeightOnlyConfig` default is version 1; version 2 remains required
    for the serialized safetensors path, so this warning is expected with
    TorchAO 0.17.0 unless upstream changes the default
  - warning investigation completed on 2026-04-19:
    `Cannot use ROCm custom paged attention kernel, falling back to Triton implementation`
    is emitted by vLLM only when its ROCm custom paged-attention selector
    rejects a shape/configuration; it was not present in the Gemma 4 E2B
    online TorchAO run, which selected `ROCM_AITER_UNIFIED_ATTN`
  - real-model TorchAO validation now has two tracked outcomes:
    `vllm.gemma4.e2b.torchao.online-real-model` passed on 2026-04-19 with
    `quantization=torchao`, `ROCM_AITER_UNIFIED_ATTN`, 10.62 GiB
    model-loading memory, and `generation_ok`; the serialized
    `vllm.gemma4.e2b.torchao.real-model` scenario still fails after
    `prepare_real_ok` during vLLM weight loading with
    `AttributeError: 'Tensor' object has no attribute 'tensor_data_names'`
  - keep TorchAO version checks metadata-only on generic vLLM startup paths so
    broken optional host TorchAO packages do not emit warning noise during
    unrelated CLI or server flows
  - keep the merged
    `0008-torchao-startup-stays-lazy.patch` valid as a multi-hunk patch; it
    now carries both the metadata-only version check path and the
    quantization-registry lazy import, and an earlier malformed carry variant
    broke real `quantization="torchao"` config verification with
    `NameError: find_spec`
  - keep the merged `0009-cli-startup-stays-runtime-light.patch` unless
    upstream makes the generic startup path import-clean on its own; it keeps
    plain `vllm --help` off the benchmark tree, the OpenAI `chat_utils`
    tool-call path, Transformers-backed `arg_utils` helpers, and the heavy
    `serve`/`launch`/`run-batch` runtime imports unless the user actually
    selected those flows
  - keep package patch application idempotent across reused `src/` trees as
    well; repeated `makepkg -f` runs during this lane left partially patched
    trees behind and caused `prepare()` to fail when a file-adding patch was
    reapplied without per-patch state
- Lemonade presentation polish
  - keep the backend table explicit about packaged ROCm/Vulkan backends after
    each relevant package rebuild
- benchmarking
  - benchmark this stack against `aur/rocm-gfx1151-bin`
  - revisit whether every maintained local optimization still earns its cost

## Repository Status

This repo is now the canonical source for:

- package definitions
- package policy
- local patch carry
- maintainer documentation
- the local pacman repo workflow

Older draft packaging trees and migration leftovers are historical inputs, not
authoritative sources.
