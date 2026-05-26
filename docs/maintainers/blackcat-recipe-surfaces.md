# Blackcat Recipe Surface Policy

Status as of 2026-05-26.

This document classifies the remaining Blackcat Informatics recipe surfaces
from the committed `upstream/ai-notes` submodule at
`3f15f9f1318491c9ee03782d8b2ebd41391de118`. It is a package-policy and
validation planning surface only; it does not add package implementations.

The package set in `policies/recipe-packages.toml`, package-local READMEs,
`docs/maintainers/update-candidates.toml`, and
`docs/maintainers/current-state.md` remains authoritative for package state.
Blackcat recipe material is advisory until this repo owns a package entry,
source pin, patch provenance, and validation gates.

## Disposition Rules

- `adopted`: the repo owns the package or package-equivalent surface and has
  recorded the required source, build, install, and smoke gates for its current
  state.
- `tracked`: the surface belongs in a future lane, and the next gate is clear.
- `blocked`: the surface needs user judgment, source-risk review, missing
  package boundaries, or host proof before a package or scenario lane can
  start.
- `rejected`: the surface should not become a local package candidate under
  the current repo policy.

Package-boundary decisions come from current package policy, the Blackcat
submodule, and the freshness ledgers. When those sources disagree, committed
package policy and freshness dispositions take precedence over recipe text.

## Adopted Package Surfaces

| Surface | Disposition | Boundary | Future gates |
| --- | --- | --- | --- |
| `stable-diffusion.cpp-vulkan-gfx1151` | `adopted` package surface; current upstream movement remains `tracked` through the stable-diffusion.cpp freshness candidate | Vulkan engine package with suffixed wrappers, local `/opt` layout, Blackcat CLIP-G patch carry, and AUR Vulkan package as the closest baseline | For source refreshes: review upstream and recursive submodule delta, apply CLIP-G patch, build, deploy/install, and rerun installed Vulkan wrapper smoke |
| Blackcat `rust_wheels` | `adopted` where concrete package entries exist | Rust-backed Python package entries such as OpenAI Harmony, orjson, cryptography, pydantic-core, tokenizers, safetensors, and watchfiles follow normal package policy | Future versions move through freshness families; do not add abstract stack-variant policy entries |
| Blackcat `native_wheels` | `adopted` where concrete package entries exist | Native Python package entries are represented directly in `policies/recipe-packages.toml` and package-local docs | Active movement stays in ordinary freshness lanes, including DuckDB, Httptools, and Yarl |
| Blackcat `source_wheels` exports | `adopted` only through equivalent system packages | PyTorch, Triton, TorchVision, AITER, and FlashAttention are repo-owned system packages rather than exported virtualenv wheels; AMD SMI is covered by TheRock/ROCm payloads unless a future audit proves a separate Python package is needed | Keep source-wheel exports out of package policy unless a missing runtime import or source audit requires a new local package |
| Qwen3-VL quantization helper packages | `adopted` for the existing package closure | `python-compressed-tensors-gfx1151`, `python-accelerate-gfx1151`, `python-auto-round-gfx1151`, and `python-llmcompressor-gfx1151` are local packages; `llmcompressor 0.10.0.2` remains rejected in the candidate ledger | Reconcile torch, Transformers, compressed-tensors, accelerate, and auto-round bounds together before any llmcompressor update |

## Remaining Candidates

| Surface | Disposition | Reason | Next gate |
| --- | --- | --- | --- |
| Qwen3-VL embedding/reranking runtime notes | `blocked` for scenario promotion | The notes depend on model-specific behavior, `trust_remote_code=True`, ViT FP32 runtime changes, FP8 E5M2 cache behavior, and host model availability that are not repo-owned validation yet | Open a scenario or vLLM patch lane only after source review, local model binding, bounded fixtures or host models, and explicit assertions are defined |
| Qwen3-VL W8A16 quantization helper script | `tracked` as a future tooling/scenario lane, not a package | The helper writes model outputs, carries ad hoc virtualenv assumptions, uses generic model-path placeholders, and needs dependency closure against the installed local packages | Sanitize path handling, remove virtualenv assumptions, add tests for output-config verification, run a model-free or fixture-backed smoke, then run host model validation |
| `llamacpp_atomic` / Atomic TurboQuant | `blocked` package candidate | Blackcat treats the branch as an evaluation side variant. It is a third-party fork branch that must not replace the maintained `ggml-org/llama.cpp` package lane without user judgment and source-risk review | Require user approval, pinned source ref, license/provenance review, package-boundary decision, benchmark target, backend coexistence story, package build, deploy/install, and installed scenario gates |
| Bootstrap tools from Blackcat scripts: `uv`, `yq`, and `ccache` | `rejected` as local package candidates | They are host build tools or workflow prerequisites, not Strix Halo runtime or package-output surfaces. Arch-family packages or normal host tooling should supply them | Keep them documented as prerequisites when needed; do not add `*-gfx1151` packages |
| Quark, AWQ, GPTQ, bitsandbytes, xFormers, and FBGEMM | `tracked` outside this lane | The ROCm inference reference keeps these as source-audit and host-validation candidates, and Lane 9 owns the dedicated triage | Cross-link only; do not resolve those package candidates in this spec branch |

## Source-Risk Policy

- Treat third-party recipe inputs as advisory until package policy records the
  source lane and validation gates.
- Use pinned source refs for package candidates. Prefer checksums for release
  archives and package-local patches for carried source changes.
- Review licenses and provenance before adding package policy for third-party
  forks or model-adjacent helper repositories.
- Treat `trust_remote_code=True` model paths as code execution. Do not promote
  scenarios using those models without source review and a bounded host gate.
- Keep private filesystem paths, local model roots, cache paths, hostnames, and
  machine-specific details out of committed docs and policy.
- Helper scripts that overwrite or create model artifacts need explicit input,
  output, overwrite, dependency, and verification contracts before they become
  repo-owned tools.

## Dispatchable Follow-Up Lanes

Implementation work should stay split into separate lanes:

1. Qwen3-VL quantization helper: create a repo-owned helper or scenario plan
   around W8A16 output verification, then validate against fixture or host
   model artifacts.
2. Qwen3-VL runtime/vLLM patch lane: source-review the ViT FP32 and FP8 E5M2
   claims, define bounded scenarios, then validate on the reference host.
3. Atomic TurboQuant decision lane: ask for user approval before package
   policy, pin and audit the fork branch, and define benchmark and coexistence
   gates.
4. Stable-diffusion.cpp source refresh: use the active freshness candidate for
   upstream `1ceb5bd`, then run the package build, deploy/install, and wrapper
   smoke gates.
5. Native wheel freshness lanes: continue DuckDB, Httptools, and Yarl through
   ordinary package-update workflow.
