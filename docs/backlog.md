# Backlog

## Packaging And Build Hygiene

- Render `amerge --preview=tree` dependency forests as visual parent/child
  trees using box-drawing branches, similar to `dust` or `lsd --tree`, instead
  of listing build-order nodes with symbolic dependency references.
- Audit the remaining upstream TheRock project coverage for `hipfort-gfx1151`
  and `mivisionx-gfx1151`. Current policy already has metadata for both
  packages, but no local staged root or local package artifact currently
  contains their expected installed payloads. Rendering them requires a fresh
  TheRock build or staged install that includes those projects.
- Resume auditing the rest of the TheRock split-package family against the
  best current CachyOS / Arch baselines.
- Add a repo-owned AOCL post-install runtime smoke. The current package lane
  has build/test coverage, but no installed-host scenario equivalent to the
  `llama.cpp` and Lemonade help-entrypoint smokes. Prefer a small check that
  proves the installed AOCL-LibM library and headers are discoverable and that
  a tiny linked program or equivalent runtime probe resolves against the
  packaged library.
- Convert remaining scripted source edits into durable patch files where
  practical.
- Revalidate provisional runtime findings and patches after the self-hosted
  rebuild completes. Use `docs/maintainers/rebuild-revalidation.md` as the
  source of pending items, rerun the named inference scenarios against the
  rebuilt installed stack, then promote reproduced items into accepted docs or
  retire items that no longer reproduce.
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
- Investigate non-eager Gemma 4 lanes before promoting any E2B compiled path.
  - keep the repo-owned helper defaults eager for E2B; 26B-A4B and 31B compiled
    probes have passed, but E2B compiled plus CUDAGraph still corrupts output
    and the no-CUDAGraph compiled path previously faulted during warmup
  - start from the `compiled-probe` scenarios under `inference/scenarios/`
    instead of treating the experiment as an ad hoc terminal-only rehearsal
- Continue Qwen3.6 FP8 MoE/shared-expert follow-up on gfx1151.
  - Qwen3.5 sampler/GDN package carry, tiny smoke coverage, and blocked-probe
    coverage for Qwen3.6 are already tracked and validated
  - treat the non-AITER path as blocked until a backend advertises gfx1151 FP8
    MoE support; the current failure is
    `No FP8 MoE backend supports the deployment configuration`
  - treat the forced-AITER path as blocked on AITER opus/gfx1151 FP8-kernel
    feature work; the current `module_quant` failure is
    `unknown type name 'mfma_adaptor'`
- Extract the official vLLM Qwen3.5/Qwen3.6 recipe scenarios into the tracked
  Qwen test plan, using
  <https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html> as the
  current upstream reference.
  - keep the existing tiny Qwen3.5 smoke and blocked Qwen3.6 FP8 MoE probes,
    but extend `inference/scenarios/vllm-qwen.toml` and catalog tests with the
    recipe-level serving surfaces rather than leaving them as chat-only notes
  - cover Qwen3.6 base serving with `--reasoning-parser qwen3` and its MTP
    speculative-decoding variant
  - cover Qwen3.5 throughput text-only serving, throughput multimodal serving,
    latency-focused MTP serving, tool-calling with `qwen3_coder`, benchmark
    client flow, OpenAI-compatible multimodal API consumption, and
    ultra-long-context / YaRN override flow
  - record the NVIDIA GB200 and AMD MI355X deployment shapes as advisory
    recipe references, while adapting runnable local scenarios to the Arch
    gfx1151 package lane and current host model cache
  - include recipe configuration checks for thinking disablement, Mamba/prefix
    caching caveats, multimodal processor kwargs, and the Mamba cache versus
    CUDAGraph capture-size failure mode
- Only revisit Gemma 4 on AITER fused-MoE if there is a concrete reason to
  move off the current TRITON unquantized-MoE lane.
  - treat any such attempt as a fresh experiment
  - do not restore the dropped vLLM-side AITER MoE padding carry by default
- Promote the remaining Gemma 4 usage scenarios only after reference-host
  validation:
  - vLLM recipe-aligned reasoning, tool-calling, structured-output, and
    benchmark-lite server flows
  - keep a dedicated follow-up for the E2B server/AsyncLLM startup fault; the
    offline eager `tools/gemma4_text_smoke.py` path for the same E2B checkpoint
    still passes, so the failure is not a model-artifact or tokenizer-path
    blocker
  - keep the E2B `kernel-probe` scenario as a tracked regression probe for the
    server fault; the forced Triton attention lane still faults and rules out
    an AITER-only explanation
  - keep the serialized `vllm.gemma4.e2b.torchao.real-model` scenario
    exploratory until the TorchAO/vLLM metadata mismatch is fixed
  - multimodal image/audio/video flows, which remain exploratory until the
    shared E2B server/AsyncLLM warmup fault is fixed
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
