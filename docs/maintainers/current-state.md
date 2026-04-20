# Current State

Status as of 2026-04-20.

## Rebuild Revalidation Boundary

Runtime and inference findings recorded before the 2026-04-20 self-hosted
rebuild confidence boundary are historical evidence until they are reproduced
against the rebuilt stack. Provisional local-origin patch rationale,
expected-failure tests, and backlog findings live in
[the rebuild revalidation ledger](rebuild-revalidation.md). Promote them back
into this file, `docs/patches.md`, or package-local docs only after
post-rebuild validation records the scenario, model binding, backend split, and
failure or pass signature.

The full native package rebuild and install completed on 2026-04-20 through
`tools/amerge` plan `20260420T045008-685264b1`, with 75 completed steps and no
remaining failed steps. Build/deploy closeout for the native stack is complete;
runtime closeout now means working through the revalidation ledger.

## Live Host State

The first full live cutover and subsequent native package rebuild completed
successfully on the reference Arch host.

The reference host's active Hugging Face cache for current validation work is
`/var/cache/hf`, not the older `/bulk/hf` cache. Current local non-GGUF model
snapshots relevant to this branch are:

- `google/gemma-4-31B-it` at
  `/var/cache/hf/hub/models--google--gemma-4-31B-it/snapshots/439edf5652646a0d1bd8b46bfdc1d3645761a445`
- `Qwen/Qwen3.5-0.8B` at
  `/var/cache/hf/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17`
- `Qwen/Qwen3.6-35B-A3B` at
  `/var/cache/hf/hub/models--Qwen--Qwen3.6-35B-A3B/snapshots/7da1103448ba36029c34ce1a9a741dfe93ee0c50`
- `Qwen/Qwen3.6-35B-A3B-FP8` at
  `/var/cache/hf/hub/models--Qwen--Qwen3.6-35B-A3B-FP8/snapshots/61a5771f218894aaacf97551e24a25b866750fc2`

Use `Qwen/Qwen3.6-35B-A3B-FP8` as the main Qwen MoE/shared-expert target for
this dev arc; it replaces the earlier Qwen3.5 122B-A10B testing and usage
target. Use `Qwen/Qwen3.6-35B-A3B` as the unquantized no-AITER control before
classifying FP8-specific failures. Both local Qwen3.6 configs advertise
`Qwen3_5MoeForConditionalGeneration` / `qwen3_5_moe`, so the maintained
Qwen3.5/GDN package carry is still relevant to this lane. The FP8 model
remains a target and blocked-probe lane, not an accepted passing smoke lane,
because the rebuilt native stack reproduces the expected Qwen3.6 FP8 probe
failures in the revalidation ledger.

The rebuilt installed stack passed the unquantized Qwen3.6 control on
2026-04-20 with the `/var/cache/hf` `Qwen/Qwen3.6-35B-A3B` snapshot,
`VLLM_ROCM_USE_AITER=0`, `VLLM_ROCM_USE_AITER_MOE=0`,
`--max-num-batched-tokens 32`, and `--gpu-memory-utilization 0.9`; the tracked
`run_inference_scenarios.py` run completed in `85.054242` seconds. The run
recorded `cuda_device_0 Radeon 8060S Graphics`,
`config_quantization_config_present false`,
`config_model_type qwen3_5_moe`, `text_config_model_type qwen3_5_moe_text`,
40 hidden layers, 256 experts, 8 experts per token, the
`full_attention:10,linear_attention:30` layer split, `Using TRITON backend for
Unquantized MoE`, `Available KV cache memory: 12.31 GiB`, `llm_init_ok`,
`generation_ok`, output text `ready`, and `basic_ok`. The same
control at the previous default `--gpu-memory-utilization 0.75` failed before
`llm_init_ok` with no available KV-cache memory, so the tracked control pins
`0.9` for this host.

Installed and validated at least once on the live host:

- generated TheRock/ROCm split package family
- AOCL layer
- optimized `python-gfx1151`
- rebuilt wheel layer
- Triton and AOTriton
- PyTorch, TorchVision, AITER, and vLLM
- `llama.cpp` HIP and Vulkan backends
- Lemonade server/app/meta packages

Current installed native package state, checked on 2026-04-20 after the full
`amerge` run completed:

- `aocl-libm-gfx1151` tracks upstream AOCL-LibM `5.2.2` and built
  successfully after installing host build dependency `scons`. The scaffold
  uses Arch's system `scons` directly and passes resolved compiler paths to
  AOCL-LibM's SCons variables rather than using the recipe's venv-local pip
  bootstrap.
- `llama.cpp-hip-gfx1151` and `llama.cpp-vulkan-gfx1151` package definitions
  track upstream llama.cpp `b8851` at commit
  `e365e658f07b63371489570dfde597f199b26c23`. The live host reports both HIP
  and Vulkan packages at `b8851-1`. The Vulkan package metadata includes
  `spirv-headers` because b8851 includes `spirv/unified1/spirv.hpp` directly.
- `python-mistral-common-gfx1151` tracks PyPI `1.11.0`; the live host reports
  `python-mistral-common-gfx1151 1.11.0-1`.
- `python-pytorch-opt-rocm-gfx1151` tracks ROCm/pytorch `release/2.11` at
  commit `8543095e3275db694084a6679bd5b61f7d2ece76`; the live host reports
  `python-pytorch-opt-rocm-gfx1151 2.11.0-6`.
- `python-amd-aiter-gfx1151` remains pinned to upstream AITER main commit
  `cf12b1381dcdec4b5d90d136a5403e718c7541ec`, which is past the latest
  released tag `v0.1.12.post1`; the package exports
  `SETUPTOOLS_SCM_PRETEND_VERSION=0.1.12.post2.dev69+gcf12b1381`, and the live
  host reports `python-amd-aiter-gfx1151 0.1.12.post2.dev69+gcf12b1381-1`.
- The rebuilt wheel layer installed with simplified native package versions:
  `python-aotriton-gfx1151 0.11.2b-1`,
  `python-triton-gfx1151 3.0.0+git0ec280cf-1`,
  `python-torchvision-rocm-gfx1151 0.26.0-3`,
  `python-torchao-rocm-gfx1151 0.17.0-1`,
  `python-transformers-gfx1151 5.5.4-1`, and
  `python-vllm-rocm-gfx1151 0.19.1-1`.
- `python-triton-gfx1151` package-manager metadata and Python wheel metadata
  now agree: pacman reports `3.0.0+git0ec280cf-1`, while
  `importlib.metadata.version("triton")` reports `3.0.0+git0ec280cf`.
- `lemonade-server` was rebuilt so its system-managed llama.cpp backend
  metadata points at `b8851`; the live host reports `lemonade-server 10.2.0-2`.

## Live Smoke Coverage

This section includes both current installed-host checks and historical smoke
records. When a result was recorded before the 2026-04-20 rebuild boundary,
the rebuild revalidation ledger controls whether that result can be promoted
as current accepted behavior.

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
- On 2026-04-20,
  `python tools/run_inference_scenarios.py --engine llama.cpp --engine lemonade --tag smoke`
  passed the tracked help-entrypoint scenarios for both `llama.cpp` backends
  and Lemonade CLI/server. That confirms installed command availability, not
  AOCL runtime behavior. After the later deploy of `llama.cpp-hip-gfx1151`
  b8851 and `python-mistral-common-gfx1151` 1.11.0, the same tracked smoke
  selection passed again with 4/4 scenarios.
- On 2026-04-20, `aocl-libm-gfx1151 5.2.2-1` and
  `aocl-utils-gfx1151 5.2.2-1` passed the package-local installed-runtime
  guard:
  `pytest packages/aocl-libm-gfx1151/tests -q -o cache_dir=/tmp/aocl-package-tests-cache`.
  The guard checks installed `libalm.so`, `libau_cpuid.so`, AOCL-LibM headers,
  `libalm.so` RUNPATH `/usr/lib`, the dynamic `libau_cpuid.so` dependency,
  and a `ctypes` call to `amd_sin(0.5)`.

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
  pinned to commit `8543095e3275db694084a6679bd5b61f7d2ece76`, with package
  version aligned to the built wheel version.
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
  Gemma 4 / Transformers `5.5.x` processor path and currently tracks PyPI
  `1.11.0` because the older host
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
- `python-vllm-rocm-gfx1151` uses upstream `v0.19.1` tarball plus the local
  Python-3.14 compatibility delta and now depends on the local
  `python-openai-harmony-gfx1151`, `python-transformers-gfx1151`, and
  `python-mistral-common-gfx1151` packages for Harmony and Gemma-4-capable
  runtime closure.
  - The v0.19.1 refresh replaced the v0.19.0 tarball, reset pkgrel to `-1`,
    and the simplified native versioning lane now produces
    `python-vllm-rocm-gfx1151-0.19.1-1-x86_64.pkg.tar.zst`.
    The upstream tarball diff from v0.19.0 to v0.19.1 was 82 files changed
    with 5061 insertions and 269 deletions, mostly Gemma 4 model/tooling
    additions plus dependency metadata updates for `transformers` and
    `compressed-tensors`. The refreshed local patch series applies cleanly.
- `python-amd-aiter-gfx1151` now carries an installed-system JIT runtime fix
  so the compiled HIP helper module can be imported from the user JIT cache
  under `~/.aiter/jit/` without requiring a manually exported `AITER_JIT_DIR`.
  The same patch also teaches the runtime to find `hipcc` via
  `/opt/rocm/bin/hipcc` and the standard ROCm env vars instead of relying on
  interactive-shell `PATH` setup.
- `python-amd-aiter-gfx1151` intentionally tracks upstream AITER main at
  `cf12b1381dcdec4b5d90d136a5403e718c7541ec` rather than rolling back to the
  latest release tag. The package records upstream freshness against
  `v0.1.12.post1` but builds the post-release main lane as
  `0.1.12.post2.dev69+gcf12b1381`.
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
  - the 2026-04-20 rebuilt installed stack revalidated the same two promoted
    scenarios against
    `/var/cache/hf/hub/models--google--gemma-4-26B-A4B-it/snapshots/7d4c97e54145f8ffd1a4dd1b4986a5015a517842`;
    the text scenario passed in `109.092445` seconds, and the server scenario
    passed in `201.40131` seconds
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
  - forced Triton and forced AITER FlashAttention attention-backend probes for
    `google/gemma-4-E2B-it`
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
  - a later explicit `--attention-backend ROCM_AITER_FA` E2B server probe on
    2026-04-20 failed earlier than the Triton-attention probe: vLLM rejected
    `AttentionBackendEnum.ROCM_AITER_FA` with `compute capability not
    supported` in 25.068717 seconds, so AITER FlashAttention remains a tracked
    feasibility blocker rather than a runnable fault-isolation lane
  - a representative exploratory multimodal probe,
    `vllm.gemma4.e2b.server.image`, failed on 2026-04-19 before any image
    request was sent: the server selected `ROCM_AITER_UNIFIED_ATTN`, loaded
    weights, initialized the encoder cache with an image budget, profiled 29
    maximum-size image items, and then hit the same ROCm GPU memory-access
    fault during engine initialization
- The 2026-04-20 compiled-path revalidation keeps eager mode as the supported
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
  - compiled-lane revalidation must use fresh `VLLM_CACHE_ROOT`,
    `TORCHINDUCTOR_CACHE_DIR`, and `TRITON_CACHE_DIR` paths or explicitly clear
    the old caches; one 26B-A4B rerun reused an Apr19 Inductor artifact from
    `/tmp/torchinductor_$USER` and failed falsely with
    `mat1 and mat2 shapes cannot be multiplied (32x5376 and 2816x8192)`
  - with fresh cache roots, `vllm.gemma4.26b-a4b.text.compiled` passed on the
    reference host in `199.338261` seconds with `enforce_eager=False`,
    `ROCM_AITER_UNIFIED_ATTN`, `Using TRITON backend for Unquantized MoE`,
    torch.compile, and CUDAGraph capture; the output was
    `These are exactly five words.`
  - the same run showed `torch.compile took 26.77 s in total`, graph capture
    completed, and the model generated the expected basic smoke output, so the
    26B-A4B offline text lane can be treated as compiled-capable after the
    Triton `AttrsDescriptor.__repr__` repair
  - with fresh cache roots, `vllm.gemma4.e2b.text.compiled` no longer failed
    with the old SyntaxError: it initialized in `507.662803` seconds, selected
    `ROCM_AITER_UNIFIED_ATTN`, spent `427.27 s` in torch.compile, captured
    graphs, reached `generation_ok`, then generated corrupted non-ASCII text
    (`docked calcS ...`) and failed the basic smoke assertion
  - with a temporary `AttrsDescriptor.__repr__` shim, the E2B compiled +
    cudagraph path got through `torch.compile` and CUDAGraph capture but
    generated corrupted text, so it is not promotable
  - with the same shim and CUDAGraph disabled, the E2B compiled path faulted
    the GPU during initialization/warmup
  - do not remove eager mode for `google/gemma-4-E2B-it`; the
    E2B compiled path still generates invalid text after the Triton repair
  - `vllm.gemma4.31b.text.compiled` passed on 2026-04-20 with fresh cache roots
    against
    `/var/cache/hf/hub/models--google--gemma-4-31B-it/snapshots/439edf5652646a0d1bd8b46bfdc1d3645761a445`
    in `382.161305` seconds with `enforce_eager=False`,
    `ROCM_AITER_UNIFIED_ATTN`, `torch.compile took 55.14 s in total`, graph
    capture in 103 seconds, and output `I have written five words.`, so the
    dense 31B instruction-tuned checkpoint is compiled-capable on the current
    installed Triton/vLLM stack
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
  - the imported warmup note's `qwen3_next.py` path is stale for vLLM 0.19.1;
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
  - after the v0.19.1 upstream refresh,
    `tools/amerge build -y python-vllm-rocm-gfx1151` completed for pkgrel
    `0.19.1.r8.d20260317.gad42886-1`, producing
    `python-vllm-rocm-gfx1151-0.19.1.r8.d20260317.gad42886-1-x86_64.pkg.tar.zst`;
    `pytest packages/python-vllm-rocm-gfx1151/tests -q` and
    `pytest tests packages/python-vllm-rocm-gfx1151/tests -q` passed against
    the freshly populated `pkg/` tree
  - the simplified native package lane is now installed as
    `python-vllm-rocm-gfx1151 0.19.1-1`; use the revalidation ledger before
    treating earlier Gemma 4 and Qwen scenario results as accepted evidence for
    the current installed stack
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
    `vllm.qwen3_5.0_8b.text.basic`,
    `vllm.qwen3_5.0_8b.text.compiled`, and
    blocked Qwen3.6 FP8 MoE kernel probes for the non-AITER backend-selection
    path and the forced-AITER `module_quant` path
  - `vllm.qwen3_5.0_8b.text.basic` failed on 2026-04-19 after model loading
    with a ROCm GPU memory-access fault. The failure is now localized past GDN
    warmup, GDN prefill/recurrent kernels, full-attention kernels,
    decoder-layer execution, model forward, logits computation, and
    hidden-state indexing.
  - the Qwen3.5 0.8B fault has a standalone sampler repro: vLLM's Triton
    `apply_top_k_top_p` filter faults on ROCm/gfx1151 for logits shaped
    `(32, 248320)` with top-k enabled and top-p `0.9`, while vLLM's existing
    PyTorch fallback completes on the same tensor.
  - `python-vllm-rocm-gfx1151` pkgrel `-27` now carries
    `0011-rocm-avoid-triton-topk-topp-sampler.patch`, routing ROCm
    top-k/top-p filtering through that PyTorch fallback. `tools/amerge build
    python-vllm-rocm-gfx1151` produced pkgrel `-27`; using that built package
    payload on `PYTHONPATH`, the standalone `(32, 248320)` sampler repro
    completed and `vllm.qwen3_5.0_8b.text.basic` passed against the
    `/var/cache/hf` Qwen3.5 snapshot in 42.948777 seconds. After installing
    pkgrel `-27`, the installed-host rerun passed in `42.52507` seconds.
  - after the self-hosted rebuild, `vllm.qwen3_5.0_8b.text.basic` passed
    again on 2026-04-20 in `72.408359` seconds with `enforce_eager=True`,
    `Using Triton/FLA GDN prefill kernel`, `Using ROCM_ATTN backend`,
    `generation_ok`, output `Ready.`, and `basic_ok`
  - the new exploratory `vllm.qwen3_5.0_8b.text.compiled` scenario passed on
    2026-04-20 in `114.935893` seconds with fresh compile caches,
    `enforce_eager=False`, `Using Triton/FLA GDN prefill kernel`,
    `Using ROCM_ATTN backend`, `torch.compile took 30.89 s in total`, graph
    capture in 7 seconds, output `Ready.`, and `basic_ok`; the Qwen3.5 text
    smoke therefore does not require eager mode under the current installed
    stack
  - the Qwen3.5 compiled run still logged
    `Cannot use ROCm custom paged attention kernel, falling back to Triton implementation`
    and the underlying `operation scheduled before its operands` diagnostic;
    because the run completed and generated the expected output, keep that as
    a non-fatal fallback marker for this lane
  - Qwen3.6 FP8 MoE is not a passing smoke lane on gfx1151 yet. With
    `VLLM_ROCM_USE_AITER=0` and `VLLM_ROCM_USE_AITER_MOE=0`, vLLM fails
    during FP8 MoE backend selection with
    `No FP8 MoE backend supports the deployment configuration`; the vLLM
    Triton and batched Triton FP8 MoE gates currently advertise ROCm FP8
    support for `gfx9`, not `gfx1151`. The rebuilt installed stack reproduced
    this finding on 2026-04-20 in `22.765256` seconds against the `/var/cache/hf`
    FP8 snapshot, with `config_quantization_config_present true` and the same
    backend-selection error.
  - The 2026-04-20 rebuilt-stack control for `Qwen/Qwen3.6-35B-A3B` passed
    unquantized with AITER disabled, `--max-num-batched-tokens 32`, and
    `--gpu-memory-utilization 0.9`; the tracked scenario completed in
    `85.054242` seconds and generated `ready`. Treat this as the current
    same-family control when comparing FP8-specific failures.
  - The forced-AITER Qwen3.6 FP8 path is also blocked. The rebuilt installed
    stack selected `Using AITER Fp8 MoE backend` on 2026-04-20, then failed
    during `aiter.jit.module_quant` compilation with
    `aiter_meta/csrc/include/opus/opus.hpp:3001:24: error: unknown type name
    'mfma_adaptor'`; the tracked expected-failure scenario completed in
    `54.760926` seconds by asserting that failure mode.
  - `python-amd-aiter-gfx1151` carries the package-side header compatibility
    needed to reach the current forced-AITER Qwen3.6 FP8 blocker:
    `0006-rdna35-hip-reduce-wave32-dpp-compat.patch` keeps the shipped
    `aiter_hip_common.h` include, the package-local tests pass, and the
    installed package's `aiter_meta/csrc/include/hip_reduce.h` no longer
    references `hip_compat.h`.
  - The first AITER gfx1151 MFMA/WMMA root-cause pass found that `gfx1151`
    defines `__GFX11__` and `__gfx1151__`, while AITER's `opus.hpp` defines
    `mfma_adaptor` only for `__GFX9__` device builds and chooses that default
    for every non-`__gfx1250__` target. AITER's alternate `wmma_adaptor` path
    is not a narrow fix: a standalone compile probe showed the relevant
    gfx1250 FP8 WMMA builtin is rejected for gfx1151 with `needs target
    feature gfx1250-insts`. Treat Qwen3.6 FP8 MoE as a documented follow-up,
    not a merge blocker for the Gemma 4 branch.
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
  - after the self-hosted rebuild, the tracked tiny TorchAO scenarios passed
    on 2026-04-20: `vllm.torchao.tiny.prepare` in `4.86572` seconds and
    `vllm.torchao.tiny.generate` in `21.412559` seconds. The generate run
    recorded `prepare_ok`, `copy_probe_ok`, `quantization=torchao`,
    `llm_init_ok`, `generation_ok`, and the expected warning markers.
  - do not treat `--execution-mode compiled` as validated for TorchAO yet. A
    direct tiny TorchAO run with `--execution-mode compiled` still initialized
    vLLM with `quantization=torchao` and `enforce_eager=True`; vLLM disabled
    torch.compile and CUDAGraphs for that quantization path, so eager remains
    effectively required unless a lower-level vLLM/TorchAO change removes that
    forced eager behavior.
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
    - `System llama-server-hip-gfx1151 llama.cpp b8851`
    - `System llama-server-vulkan-gfx1151 llama.cpp b8851`

## Known Deferred Follow-up Work

- `python-flydsl-gfx1151`
  - blocked on the current `rocm-llvm-gfx1151` MLIR development surface being
    insufficient for downstream FlyDSL packaging
- package hygiene
  - remove remaining embedded build-path leakage where still present in
    PyTorch and vLLM
  - convert remaining scripted source edits into durable patch files where
    practical
- vLLM HIP `CMAKE_ARGS` flag-forwarding follow-up
  - a trial patch that taught `setup.py` to `shlex.split()` quoted
    `CMAKE_ARGS` and injected `CMAKE_HIP_FLAGS` did route extra compiler
    flags into the HIP compile lane, but it also made both vLLM build attempts
    fail in `csrc/sampler.hip` on gfx1151 with:
    `Invalid dpp_ctrl value: wavefront shifts are not supported on GFX10+`
  - treat that compile failure as the current blocker before attempting any
    further quoted-`CMAKE_ARGS` HIP flag forwarding
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
