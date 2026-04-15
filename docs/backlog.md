# Backlog

## Packaging And Build Hygiene

- Convert remaining scripted source edits into durable patch files where
  practical.
- Tighten package hygiene for embedded build paths in PyTorch and vLLM.
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
- Extend the now-validated Gemma 4 `-it` offline smoke path into:
  - OpenAI-compatible server validation
  - reasoning-parser validation (`--reasoning-parser gemma4`)
  - tool-calling validation (`--tool-call-parser gemma4`,
    `--enable-auto-tool-choice`, Gemma 4 tool chat template)
- Investigate the two remaining warnings on the now-passing TorchAO helper path:
  - `Stored version is not the same as current default version`
  - `Cannot use ROCm custom paged attention kernel, falling back to Triton implementation`
- After those warning investigations, validate at least one real-model TorchAO
  workload instead of stopping at the tiny local Llama helper. Prefer either:
  - an upstream TorchAO-quantized checkpoint, or
  - a local quantized real small model exercised through `vllm serve` /
    OpenAI-compatible API flow
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

## Benchmarks

- Benchmark this stack against `aur/rocm-gfx1151-bin`.
- Include a `llama.cpp` long-context sweep using the Strix Halo Home Lab wiki
  method as a reference point:
  - <https://strixhalo.wiki/AI/llamacpp-performance#long-context-length-testing>
- Use at least these GGUF models:
  - `unsloth/gemma-4-E2B-it-GGUF:UD-Q6_K_XL`
  - `unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q4_K_XL`
  - `unsloth/Qwen3.5-2B-GGUF:UD-Q6_K_XL`
  - `unsloth/Qwen3.5-122B-A10B-GGUF:UD-Q4_K_XL`
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
