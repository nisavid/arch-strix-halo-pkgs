# Current State

Status as of 2026-04-14.

## Live Host State

The first full live cutover completed successfully on the reference Arch host.

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

## Important Package Decisions

- `python-gfx1151` is rebased onto Arch/Cachy Python `3.14.4`, not the
  recipe's older Python `3.13.x` pin.
- `amdsmi-gfx1151` now installs an `amd_smi.pth` import hook into Python
  `site-packages`, so Python `3.14` can import the ROCm-shipped `amdsmi`
  module from `/opt/rocm/share/amd_smi` without extra `PYTHONPATH` glue on the
  host.
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
- The current host Gemma 4 tokenizer failure is not a repo-package design gap;
  it is a live-system drift issue. The host still had
  `python-sentencepiece-gfx1151 0.2.1.r8.d20260317.gad42886-1` installed, and
  that older installed extension still linked against stale host
  `sentencepiece` / `protobuf` / `abseil` shared libraries.
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
- The host `python-torchao-rocm` package currently fails to load its optional
  `_C.abi3.so` extension because the shipped binary is not import-clean
  against the installed PyTorch runtime: it is missing a usable `torch/lib`
  runpath and still fails on unresolved `at::TensorBase::const_data_ptr`
  symbols once the torch shared libraries are made visible. Generic vLLM
  startup is still being tightened to avoid importing TorchAO eagerly on
  non-TorchAO code paths. The first lazy-import boundary removed the
  model-loader version-check import, but `vllm --help` still reached
  `TorchAOConfig` through the generic quantization registry. Treat the host
  TorchAO defect as optional-feature debt, but keep carrying lazy-import
  boundaries until generic CLI/help/server startup no longer surfaces the
  warning. The TorchAO Python-level APIs vLLM actually touches
  (`config_from_dict`, `quantize_`, and packed-tensor conversion) still work
  on the reference host. A third startup-noise fix is also required on this
  lane: plain `vllm --help` must stay off the benchmark latency import path,
  because `vllm.entrypoints.cli.benchmark.latency` imports
  `vllm.benchmarks.latency` at module import time and that path drags in
  `EngineArgs` plus enough generic config/model code to resurface the same
  optional TorchAO warning. A fourth startup-noise fix is also required on
  this lane: `vllm.entrypoints.openai.engine.protocol` must not import
  `vllm.entrypoints.chat_utils` at module import time just to build tool-call
  IDs, because that chat-utils path drags in Transformers chat/model helpers
  and can still reach `transformers.quantizers.quantizer_torchao` during
  otherwise generic CLI startup. A fifth startup-noise fix is also required on
  this lane: `vllm.engine.arg_utils` must not import
  `vllm.transformers_utils.config`, `gguf_utils`, `repo_utils`, and `utils`
  at module import time, because those helpers are only needed in runtime
  methods but their eager import immediately pulls in Hugging Face
  `transformers` and its quantizer registry. A sixth startup-noise fix is
  also required here: plain top-level `vllm --help` must not import
  `vllm.entrypoints.utils` runtime helpers or the heavy `serve`/`launch`/
  `run-batch` command trees just to print the subcommand list.
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
  - for text-only workloads, set `--limit-mm-per-prompt image=0,audio=0` to
    skip unnecessary multimodal profiling and encoder reservations
  - for image-only workloads, set `--limit-mm-per-prompt audio=0`
  - for throughput-oriented serving, `--async-scheduling` is recommended
  - for benchmark runs, disable prefix caching with
    `--no-enable-prefix-caching` to get more consistent measurements
  - for Gemma 4 thinking/tool-calling server flows, pair
    `--reasoning-parser gemma4`, `--tool-call-parser gemma4`,
    `--enable-auto-tool-choice`, and the
    `examples/tool_chat_template_gemma4.jinja` template instead of assuming
    the model's default chat template is sufficient
- The current validated Gemma 4 local smoke workflow on Strix Halo is:
  - use `google/gemma-4-E2B-it` or `google/gemma-4-31B-it`
  - render the prompt with the checkpoint's chat template
  - run vLLM in text-only mode with
    `limit_mm_per_prompt={"image": 0, "audio": 0, "video": 0}`
  - keep `enforce_eager=True` for the current local smoke path
  - expect the 31B instruction-tuned checkpoint to emit an empty thought block
    prefix when thinking is disabled, matching the upstream Gemma 4 model card
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
  - only revisit the external `python-torchao-rocm` package if this repo needs
    working TorchAO custom ops or `--quantization torchao` paths that truly
    depend on the native `_C` extension rather than the Python-level APIs
  - keep TorchAO version checks metadata-only on generic vLLM startup paths so
    broken optional host TorchAO packages do not emit warning noise during
    unrelated CLI or server flows
  - keep `TorchAOConfig` behind a quantization-specific lazy import in the
    generic registry as well; vLLM currently probes quantization backends
    during config validation, and that path must not import TorchAO unless
    `quantization == "torchao"`
  - keep plain `vllm --help` off the benchmark latency import path too; the
    benchmark command tree should only load when the user actually invokes
    `vllm bench ...`
  - keep the OpenAI engine protocol module off the `chat_utils` import path on
    generic startup too; tool-call ID helpers can be imported lazily when a
    tool call is actually serialized
  - keep `vllm.engine.arg_utils` off the `vllm.transformers_utils.*` import
    path on generic startup too; those helpers should load only inside the
    methods that actually need them
  - keep top-level `vllm --help` off the shared `entrypoints.utils` runtime
    path and off heavy subcommand registration imports too; generic help only
    needs static command metadata, not the serving/runtime trees
  - keep package patch application idempotent across reused `src/` trees as
    well; repeated `makepkg -f` runs during this lane left partially patched
    trees behind and caused `prepare()` to fail when a file-adding patch was
    reapplied without per-patch state
- vLLM/Gemma follow-up
  - extend the current verified offline `-it` smoke path into API-server,
    reasoning-parser, and tool-calling validation using the official Gemma 4
    recipe flags and chat template
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
