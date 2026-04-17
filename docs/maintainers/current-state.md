# Current State

Status as of 2026-04-15.

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
- The local package/default ROCm lane no longer treats
  `google/gemma-4-26B-A4B-it` as fully validated:
  - the text-only repair lane is still the same one operationally:
    `--limit-mm-per-prompt {"image":0,"audio":0,"video":0}`,
    `--max-model-len 128`, `--max-num-batched-tokens 32`, and
    `--gpu-memory-utilization 0.75`
  - leaving `video` implicit in `--limit-mm-per-prompt` was enough to send
    vLLM back into multimodal warmup on this host and reproduce the earlier
    GPU memory-access fault during engine initialization
  - the latest host rerun on 2026-04-16 showed the narrower remaining failure:
    engine init and `/v1/models` succeeded, but both offline and basic-server
    smokes emitted corrupted text
  - root cause points at the 704-wide Gemma 4 MoE intermediate shape on the
    ROCm AITER fused-MoE path: the local AITER-side `torch_moe` fallback was
    firing only after vLLM had already shuffled the expert weights into AITER
    runtime layout, which is not a safe place to switch execution kernels
  - the repo now carries the upstream-style vLLM-side fix in
    `0010-rocm-pad-gemma4-moe-intermediate-for-aiter.patch`, which pads the
    intermediate size before the AITER weight shuffle so
    `google/gemma-4-26B-A4B-it` can stay on the intended fused-MoE path
  - the next live rerun on 2026-04-16 narrowed the remaining fault again:
    AITER selected the unquantized CK 2-stage path, JIT-built the stage-2
    kernel successfully, then faulted on first use with `ksplit=0`
  - the repo now also carries
    `0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch` in
    `python-amd-aiter-gfx1151` to normalize that no-split sentinel at the CK
    launch boundary and keep stage 2 aligned with the computed `ksplit`
  - host revalidation is still required before treating the 26B-A4B lane as
    solved
  - a 2026-04-17 source audit also left three carries needing re-review
    before they should be treated as proven root-cause fixes:
    `python-amd-aiter-gfx1151/0001-gfx1151-rdna35-header-compat.patch`,
    `python-amd-aiter-gfx1151/0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch`,
    and
    `python-vllm-rocm-gfx1151/0007-rocm-enable-gfx1x-aiter-and-prefer-it-for-gemma4.patch`
- The tracked host-side follow-up helper for OpenAI-compatible server smokes is
  now `tools/gemma4_server_smoke.py`.
  - `--mode basic` launches
    `python -m vllm.entrypoints.openai.api_server` from the active interpreter
    and sends a plain `/v1/chat/completions` request, so the smoke does not
    depend on interactive-shell `PATH` setup
  - for the current `google/gemma-4-26B-A4B-it` repair lane, the helper now
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
- The reference host has now verified all three OpenAI-compatible Gemma 4
  server flows with `google/gemma-4-E2B-it`:
  - basic chat completion passes with the helper's default `--max-model-len 512`
  - reasoning parsing passes with `--mode reasoning`, `--reasoning-parser gemma4`,
    `skip_special_tokens=false`, and `--max-model-len 1024`; the returned
    OpenAI message now splits cleanly into `message.reasoning` and
    `message.content`
  - tool-calling passes with `--mode tool`, `--reasoning-parser gemma4`,
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
  - investigate the remaining TorchAO config warning on that path:
    `Stored version is not the same as current default version`
  - investigate the remaining generation-path warning on that path:
    `Cannot use ROCm custom paged attention kernel, falling back to Triton implementation`
  - after those two warning investigations, validate at least one real-model
    TorchAO workload rather than stopping at the tiny local Llama helper
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
