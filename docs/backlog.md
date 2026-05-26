# Backlog

## Packaging And Build Hygiene

- The llama.cpp selected-token logits branch is adopted. Both packaged backends
  stay on upstream `b9222` at pkgrel `3` and carry a shared generic
  `/completion` `token_logits` patch that returns every requested raw token
  logit from full-vocabulary logits, including prompt-final selected logits
  when no generation budget remains, preserves original token bytes, and caps
  each request at 1024 selected token IDs. Renderer tests, package-local tests,
  source preparation, `tools/amerge` build plan `b664ef40`, deploy plan
  `b9b88117`, installed backend smoke, and direct HIP/Vulkan `/completion`
  smokes passed for the adopted artifacts.
- TheRock 7.13 stable is adopted. Upstream ROCm/TheRock published the stable
  `therock-7.13` release at
  `6d2136cd12be28c6251eb38c700e980c8c2f8cf6`; the generated
  `therock-gfx1151` split package now renders as `7.13.0-2` from a real staged
  7.13 root. Package build, repo-local publish, deploy/install, ROCm host
  visibility, MIGraphX payload/import-order smokes, downstream installed
  imports, and the affected Torch-MIGraphX compiled scenario smokes passed on
  2026-05-18.
- The 2026-05-18 freshness follow-up bundle is adopted. It updates NumPy
  `2.4.6`, AOTriton `0.12b`, llama.cpp `b9222`, stable-diffusion.cpp
  `r629.gcaa823a`, PyTorch `2.12.0`, TorchVision `0.27.0`, and the vLLM
  compatibility rebuild `0.21.0-3`; Lemonade backend metadata now points at
  the llama.cpp `b9222` system backends. Source verification, package source
  preparation, package builds, deploy/install, installed Python smokes, ROCm
  GPU tensor smoke, stable-diffusion.cpp wrapper startup, llama.cpp/Lemonade
  smoke scenarios, and the affected Qwen3.5 vLLM scenario passed on
  2026-05-19. Watchfiles `1.2.0-1` was adopted earlier in the same branch with
  source verification, package build, deploy/install, and installed import
  smoke evidence.
- The 2026-05-25 AITER 0.1.14 stable refresh is adopted. Source metadata now
  tracks upstream tag `v0.1.14`, source verification, source preparation,
  package-local tests, package build, deploy/install, installed AITER JIT
  smoke, constrained Qwen3.5 vLLM smoke, and the default
  `vllm.qwen3_5.0_8b.text.basic` live scenario passed before and after the
  tiny-smoke memory reservation was tightened. The closeout also tightened
  small-model vLLM smoke reservations so tiny correctness probes no longer ask
  vLLM to reserve 75% of the whole device by default.
- The DuckDB/yarl/httptools native-wheel refresh is adopted.
  `python-duckdb-gfx1151` now tracks DuckDB `1.5.3`,
  `python-httptools-gfx1151` now tracks httptools `0.8.0`, and
  `python-yarl-gfx1151` now tracks yarl `1.24.2`. The native-wheel renderer
  emits `/usr/bin/python` for generated build and installer calls, the
  httptools system-llhttp patch is refreshed for the 0.8.0 source, package
  build, published-repo, deploy/install, installed package smokes, affected
  aiohttp/uvicorn/vLLM import smokes, and the Qwen3.5 vLLM live scenario
  passed on 2026-05-26.
- The 2026-05-26 AOCL 5.3 refresh is adopted. AOCL-Utils now tracks upstream
  and AUR `5.3.0`, and AOCL-LibM now tracks upstream `5.3` with the refreshed
  SCons amdclang compatibility patch. Package builds produced
  `aocl-utils-gfx1151 5.3.0-1` and final `aocl-libm-gfx1151 5.3-1`; the
  rebuilt AOCL-LibM archive is published, and deploy/install, AOCL-Utils
  `pkg-config`, installed `libalm` runtime, and downstream stable-diffusion.cpp
  Vulkan wrapper smokes passed.
- The Lemonade 10.6.0 fork-main refresh is adopted. The source lane pins
  `nisavid/lemonade` fork main at
  `b608a74d0604f96786de59d65cb0ba27b05db0c6`, aligned with canonical upstream
  and AUR `10.6.0` baselines. This fork commit includes the pinned-backend
  lifecycle and reranking error-message fixes that were temporarily carried in
  the package lane, so those package-local patches are removed. Recipe render,
  package-local tests, full pytest, package build, deploy/install, installed
  pacman verification, and the selected-logit zerank scenario passed for
  `lemonade-server 10.6.0-5` and `lemonade-app 10.6.0-4`; the live scenario
  run is recorded at `docs/worklog/inference-runs/20260526T-current-zerank`.
- Lemonade fork 13b1af2 follow-up: the 2026-05-26 freshness gate found
  `nisavid/lemonade` fork main at
  `13b1af25f84cf08ad5f8bf0ec58980bdfc09c9e7` after the adopted
  `b608a74d0604f96786de59d65cb0ba27b05db0c6` package source lane. Review the
  fork range against the Strix Halo llama.cpp backend integration and app/server
  package carry, refresh package metadata, build, deploy/install, run installed
  service smokes, and rerun affected reranking or backend scenarios before
  adoption.
- llama.cpp b9333 follow-up: the 2026-05-26 freshness gate found upstream
  `b9333` after the adopted `b9222` backend package lane, with AUR
  `llama.cpp-hip` at `b9326-1`. Treat this as superseding the earlier `b9279`,
  `b9305`, and `b9330` observations: review the release range, update both
  packaged backends and Lemonade backend metadata, rebuild, deploy/install, run
  installed backend smokes, and rerun Lemonade service plus affected inference
  scenarios before adoption.
- ROCm PyTorch release/2.12 26872de follow-up: the 2026-05-21 closeout
  freshness gate found `ROCm/pytorch` release/2.12 at
  `26872debb4452ea6dc898288618a15595e2317d9` after the adopted
  `4ddfe99d6da426414b7f0e587cdb1910f1c23eb3` package lane. Review the branch
  delta against the local patch carry, rebuild PyTorch and affected native
  consumers, deploy/install, and rerun installed GPU plus affected vLLM
  scenario validation before adoption.
- stable-diffusion.cpp 1ceb5bd follow-up: the 2026-05-26 freshness gate found
  upstream master at `1ceb5bd9df7784bcdf67dd9ed8bf0198b542ebc9` after the
  adopted `caa823a8c06a51288f0a01bb29e9bd8bcec30a8a` package lane. Treat this
  as superseding the earlier `3a8788c` and `a397e03` follow-ups: review the
  source and submodule delta, refresh package metadata, rebuild with the
  carried CLIP-G patch, deploy/install, and rerun the installed Vulkan wrapper
  smoke before adoption.
- Transformers 5.9.0 follow-up: the 2026-05-21 closeout freshness gate found
  PyPI and upstream tag `transformers 5.9.0` after the current `5.8.1` package
  lane. Review dependency metadata against tokenizers, safetensors, Hugging
  Face Hub, and the local vLLM/model-surface package closure, then rebuild,
  deploy/install, run installed imports, and rerun affected vLLM scenarios
  before adoption.
- The 2026-05-18 Python 3.14.5 rebuild lane is adopted. `python-gfx1151`
  now tracks CPython `3.14.5` with Arch `python 3.14.5-1` as the integration
  baseline. Source verification, package source preparation, package build,
  deploy/install, installed Python/import smokes, ROCm host visibility, and
  focused vLLM/TorchAO and Qwen3.5 live scenarios passed on 2026-05-18.
- The 2026-05-18 source-lane contract cleanup is adopted. AITER now tracks the
  prerelease-enabled GitHub release lane at `v0.1.14-rc0`, and the Lemonade
  bundle now tracks the fork default branch at
  `3a1a0dff2d5fe24f4369f91e76b8587b5c703e78`, aligned with upstream stable
  `10.5.0`. Package build, publish/install, installed smokes, Lemonade
  pooling/rerank scenarios, and the promoted Gemma 4 26B A4B vLLM text/server
  scenarios passed on 2026-05-18. Future movement should come through the
  normal source-lane freshness contracts rather than reopening this bundle.
- The 2026-05-15 refresh bundle is adopted. Source metadata is updated for
  vLLM 0.21.0, AITER main
  `7cfe51983cd9dd55c0355e34fb614e7c0de44e6e`, llama.cpp `b9165`, and
  stable-diffusion.cpp `r604.g0b82969`. Source verification and package source
  preparation passed for the affected packages. Package build produced
  `llama.cpp-hip-gfx1151 b9165-1`, `llama.cpp-vulkan-gfx1151 b9165-1`,
  `python-amd-aiter-gfx1151 0.1.14rc1.dev27+g7cfe51983-1`,
  `python-vllm-rocm-gfx1151 0.21.0-1`, and
  `stable-diffusion.cpp-vulkan-gfx1151 r604.g0b82969-1`. Deploy/install and
  installed-smoke passed on 2026-05-17. The first vLLM live-scenario follow-up found a `triton.knobs`
  incompatibility in vLLM's JIT monitor after a constrained Qwen probe got
  past model loading. `python-vllm-rocm-gfx1151 0.21.0-2` now builds with a
  guard for ROCm Triton runtimes without `triton.knobs`; deploy/install,
  installed-smoke, and a constrained Qwen vLLM smoke passed for pkgrel 2. The
  promoted default live-scenario rerun passed after the host freed enough VRAM
  for the default 75% vLLM reservation:
  `vllm.gemma4.e2b.server.basic` passed in `141.647271` seconds and
  `vllm.qwen3_5.0_8b.text.basic` passed in `42.133449` seconds at
  `docs/worklog/inference-runs/20260517T232711`.
- The 2026-05-14 refresh is adopted. It has source-update, package-build,
  deploy/install, installed-smoke, llama.cpp scenario-runner smoke, and
  affected Gemma 4 vLLM live-scenario evidence for llama.cpp `b9145`, AITER
  main `d50194cae28f2e22f4dfff19a86577fe2fcbca27`, and Transformers 5.8.1.
  The AITER and Transformers PKGBUILDs now call `/usr/bin/python` directly so
  bytecode generation stays out of agent-local Python wrappers and private
  pycache roots. Keep follow-up work on separate backlog lines instead of
  reopening this closed update bundle.
- The 2026-05-14 sweep rejected ROCm PyTorch release/2.11 at
  `96bfee122869125d32aa4ec9acc8c3597059188b` because the range does not overlap
  the local gfx1151 package carry, and rejected TorchVision 0.27.0 because its
  published metadata requires `torch==2.12.0`.
- The 2026-05-07 freshness sweep found a new refresh bundle now prepared in
  source metadata: AITER main
  `086cd0aef432233e604891224b4a39645b2e24c2`, llama.cpp `b9050`,
  stable-diffusion.cpp `r596.g90e87bc`, Transformers 5.8.0,
  mistral-common 1.11.2, cryptography 48.0.0, orjson 3.11.9, accelerate
  1.13.0, and auto-round 0.12.3. Package build, deploy/install, and installed
  smokes passed for the bundle. The promoted Gemma 4 vLLM scenarios also
  passed on 2026-05-10 with
  `HF_HUB_CACHE=<testing HF hub cache root>`, so the refresh bundle is
  adopted in `docs/maintainers/update-candidates.toml`.
- The 2026-05-10 follow-up refresh is adopted. It has source-update,
  package-build, deploy/install, installed-smoke, and affected live-scenario
  evidence for AITER 0.1.13, Lemonade 10.4.0, llama.cpp b9101, ROCm PyTorch
  release/2.11 at `5223630054ce5ecd7b774d0ea31f2a1b472fb9b3`, Blackcat
  ai-notes at `3f15f9f1318491c9ee03782d8b2ebd41391de118`, Torch-MIGraphX at
  `b94b985586a051fbee19aefe8c934bb7c1a9df0a`, and vLLM 0.20.2. Package build
  completed through `tools/amerge` plan `20260510T185935-9cefeddf`;
  deploy/install completed through plans `20260510T201114-f3f30a0d`,
  `20260511T081325-ff707e38`, and `20260511T082929-52430ccd`; vLLM was
  rebuilt after the corrected PyTorch deploy through plan
  `20260511T081446-f56bde47`; and affected live scenarios passed in
  `docs/worklog/inference-runs/20260511T083036`.
- The local python-pydantic ABI lane is adopted. `python-pydantic-core-gfx1151`
  now renders as `2.46.4-1`, aligned with Arch `python-pydantic-core
  2.46.4-1` and the installed `python-pydantic 2.13.4-1` ABI. PyPI
  pydantic-core 2.47.0 remains a reviewed baseline cursor, not an adopted
  source, until this repo owns a matching local `python-pydantic` lane.
  Source verification, source preparation, focused tests, `tools/amerge` build
  plan `1313f3a8`, installed pydantic smoke, and affected local consumer
  imports passed on 2026-05-26.
- The 2026-05-03 refresh candidates are adopted as one branch: vLLM 0.20.1,
  llama.cpp b9010, and AITER main
  `51f3d2b6968360fba7772208025e5c07756121ba`. `tools/amerge` plan
  `20260503T045139-18169e0b` built `python-vllm-rocm-gfx1151 0.20.1-1`, both
  llama.cpp backends at `b9010-1`, and
  `python-amd-aiter-gfx1151 0.1.12.post2.dev171+g51f3d2b69-1`. The deployed
  host passed installed smokes and affected live scenarios on 2026-05-03;
  exact versions, smokes, and scenario evidence are recorded in
  `docs/maintainers/current-state.md`. Keep follow-up work on separate backlog
  lines instead of reopening this closed update bundle.
- Build and host-validate the active 2026-04-28 update branch. Completed on
  2026-04-29. The branch updates vLLM 0.20.0, llama.cpp b8966, ROCm PyTorch
  release/2.11 at 9413e9b, AITER d679e288, Lemonade 10.3.0, and Transformers
  5.7.0. The source-update, package-build, deploy/install, installed-smoke,
  service-smoke, and live-scenario gates are recorded in
  `docs/maintainers/current-state.md` and the candidate dispositions are now
  adopted in `docs/maintainers/update-candidates.toml`. Keep follow-up work
  on separate backlog lines instead of reopening this closed update bundle.
- The 2026-04-30 refresh candidates are adopted as one branch: AITER main
  `a0f25393903f5412b0fb997d5b825a0aeb257466`, llama.cpp `b8992`,
  `mistral-common 1.11.1`, and ROCm PyTorch release/2.11 at
  `443606eb94430d90554ab4c21202494576afedce`. `tools/amerge` plan
  `20260430T232524-81972211` built Lemonade server, both llama.cpp backends,
  `python-mistral-common-gfx1151`, PyTorch, AITER, FlashAttention, TorchAO,
  Torch-MIGraphX, TorchVision, and vLLM. The deployed host passed installed
  smokes and live scenarios on 2026-05-01; exact versions, smokes, and scenario
  evidence are recorded in `docs/maintainers/current-state.md`. Keep follow-up
  work on separate backlog lines instead of reopening this closed update
  bundle.
- The 2026-05-01 policy-change freshness sweep found one active update
  candidate that should preempt ordinary backlog work after the current
  package-policy slice lands: AITER main
  `a85874151dc9a9e607598b8b73f83c6fab954a6b`. The reviewed head is recorded in
  `policies/package-freshness.toml`; the active disposition and gate label are
  in `docs/maintainers/update-candidates.toml`.
  - `AITER a8587415 source-update lane`: review the MLA decode Gluon and mHC
    synchronization range, build and install the package, run the installed JIT
    smoke, and run affected vLLM scenario validation.
- Blackcat recipe surface policy is centralized in
  `docs/maintainers/blackcat-recipe-surfaces.md`. The current package set
  already adopts the concrete stable-diffusion.cpp, Rust wheel, native wheel,
  source-wheel-equivalent, and Qwen3-VL tooling-helper package surfaces
  represented in `policies/recipe-packages.toml`. Remaining dispatchable work
  is separate: Qwen3-VL quantization helper tracking, Qwen3-VL runtime/scenario
  blocking gates, Atomic TurboQuant user/source-risk blocking gates, the active
  stable-diffusion.cpp source refresh, and future native-wheel freshness lanes
  found by the normal sweep.
- Newly discovered ROCm inference candidates from
  `docs/maintainers/rocm-inference-reference.md` belong near the top of this
  backlog, but they are not validated package commitments until their source
  audit and host gates pass.
  - Open WebUI STT CTranslate2 lane: adopted and validated. The package follows
    OpenNMT CTranslate2 4.7.2 with upstream `WITH_HIP=ON` for `gfx1151`.
    Package-build proof passed through `tools/amerge build
    ctranslate2-gfx1151` on 2026-05-24, producing both split packages after
    CMake used ROCm clang directly, the optional CLI target was disabled, the
    exact pybind11 build pin was relaxed, and package Python calls used
    `/usr/bin/python`. Both split packages are published to and installed from
    the local repo, `amerge` selects both recipe-declared split outputs for
    root-target deploys, installed Python smokes see one ROCm device through
    CTranslate2, and the Open WebUI/faster-whisper STT consumer smoke passes on
    the ROCm path.
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
  - Candidate follow-ups from the 2026-05-26 Lane 9 source audit are ranked
    below. Keep each marked as requires host validation before adding a package
    or promoting a scenario; package implementation waits for the runtime-base
    prerequisite lanes if they change the Python/ROCm stack.
    - GPTQ, next implementation lane: run the retained
      `vllm.qwen3_5.4b-gptq-int4.text.basic` scenario against the installed
      gfx1151 stack after pinning the RafaDom model revision, license
      metadata, and provenance/terms review. The current vLLM support matrix
      lists GPTQ as unsupported on AMD GPU, so treat local installed scenario
      results as the promotion gate. No new runtime package is expected for
      prequantized GPTQ inference; promote only after vLLM ROCm extensions
      import, generation passes, and source/build/install/live states are
      recorded separately.
    - Quark: track as a vLLM model-artifact and optional authoring-tool lane,
      not as a `python-vllm-rocm-gfx1151` runtime dependency. The package lane
      is blocked until the chosen `amd-quark` release has public source
      provenance or an explicit source pin, and until Python 3.14 plus NumPy
      compatibility is resolved. A consumer-only lane can start with a pinned
      Quark-exported model and a bounded vLLM generation smoke.
    - bitsandbytes: track a separate source-built
      `python-bitsandbytes-gfx1151` package candidate. Upstream ROCm support is
      preview but names `gfx1151`; do not adopt PyPI or PyTorch-index binary
      wheels. Required gates are a `COMPUTE_BACKEND=hip` build for `gfx1151`,
      installed `python -m bitsandbytes`, direct 4-bit and 8-bit PyTorch
      smokes, a pinned Transformers model smoke, and a bounded vLLM
      BitsAndBytes smoke.
    - AWQ: track as exploratory Qwen text coverage only. Keep native AWQ,
      compressed-tensors-format AWQ models, and deprecated AutoAWQ tooling
      separate; do not package AutoAWQ for this lane. Required gates are a
      pinned AWQ model revision/license, `VLLM_USE_TRITON_AWQ` backend evidence
      where applicable, LLM init, generation, and selected-backend assertions.
    - xFormers: track as a future source-built attention package only when a
      concrete consumer needs it or upstream publishes explicit `gfx1151`
      evidence. Required gates are pinned source and submodules, local HIP
      extension build, linkage/private-path inspection, `python -m
      xformers.info`, and direct fp16/bf16 memory-efficient-attention
      correctness smokes before any consumer scenario.
    - FBGEMM: track as a future package candidate, not as a PyTorch bundle.
      Current public ROCm evidence targets CDNA/MI300-class systems and the
      GenAI code is moving toward `meta-pytorch/MSLK`. Required gates are a
      package-boundary decision, pinned source/submodules, source build for
      `gfx1151`, shared-library inspection, import/op smoke, and a vLLM or
      Transformers consumer path that proves value over existing TorchAO,
      compressed-tensors, AITER, and FlashAttention lanes.
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
- Continue Qwen3.6 sparse-model and quantization follow-up on gfx1151.
  - Qwen3.5 sampler/GDN package carry, tiny smoke coverage, and blocked-probe
    coverage for Qwen3.6 are already tracked and validated
  - validate the small FP8 safetensors exploratory probe before promoting the
    lane to smoke coverage:
    `vllm.qwen3_5.0_8b-fp8.text.fp8-safetensors-blocked`
  - compare FP8 probe outcomes against the accepted unquantized no-AITER
    `Qwen/Qwen3.6-35B-A3B` control, which currently passes with
    `--max-num-batched-tokens 32` and `--gpu-memory-utilization 0.9`
  - keep the RedHatAI Qwen3.6 NVFP4 probe blocked on local ROCm vLLM ModelOpt FP4
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
- Keep DFlash speculative decoding gated on installed validation of the vLLM
  0.20.0 update lane.
  - the active update branch uses upstream vLLM 0.20.0 DFlash model/runtime
    and speculators parser support instead of carrying a narrow local parser
    backport
  - promote DFlash scenarios only after the 0.20.0 package build, install, and
    reference-host smoke gates pass
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

## Repository Hygiene

- Normalize package patches so reviewable source changes live as patch files.
- Remove or ignore transient session/worklog docs once durable content has been
  extracted.

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
  - `Qwen/Qwen3.6-35B-A3B` for the main non-GGUF vLLM Qwen MoE lane
  - `surogate/Qwen3.5-0.8B-FP8` for the small FP8 safetensors probe
  - `RafaDom/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-v2-GPTQ-Int4-HQ`
    for the GPTQ Int4 safetensors probe
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
