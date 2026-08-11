# ROCm Runtime Compatibility Line

Retrieved: 2026-08-11

## Question

What current first-party version and dependency constraints determine a
coherent runtime line across ROCm PyTorch 2.13, TorchVision 0.28, AOTriton
0.13b, TorchAO 0.18, AITER 0.1.19.post2, vLLM 0.27, Transformers 5.15, and
their directly coupled quantization and runtime dependencies?

## Decision gist

The versions do not form one fully first-party-validated ROCm line as written.
Use the following as the candidate `gfx1151` serving core, then require a
source build and host validation before adoption:

- ROCm PyTorch 2.13.0, its ROCm Triton 3.8.0 source pin, AOTriton 0.13b,
  and TorchVision 0.28.0
- vLLM 0.27.0 built from source, Transformers 5.15.0, safetensors 0.8.0,
  mistral-common 1.11.7, and compressed-tensors 0.17.0

Keep TorchAO 0.18.0 optional. Keep AITER 0.1.19.post2 plus FlyDSL 0.3.0
experimental and outside the required `gfx1151` vLLM path. Keep llmcompressor
and AMD Quark authoring tooling out of the serving environment until upstream
metadata admits the core versions and Python 3.14 respectively.

This is a compatibility decision, not validation evidence. Upstream ROCm
guidance for Instinct/CDNA remains advisory for Strix Halo until a local
installed scenario passes.

## Hard framework constraints

| Component | Current first-party constraint | Result for the candidate line |
| --- | --- | --- |
| ROCm PyTorch | The current `release/2.13` branch reports `2.13.0`. At retrieved head [`4be323c`](https://github.com/ROCm/pytorch/commit/4be323cffdd92aeb272b15958ebafe9a5e6c6a33), its CI files select ROCm Triton version `3.8.0` at [`4cff872`](https://github.com/ROCm/triton/commit/4cff872ced001ea92d9fcf05b3f6517e2b486d19). Its [AOTriton CMake contract](https://github.com/ROCm/pytorch/blob/4be323cffdd92aeb272b15958ebafe9a5e6c6a33/cmake/External/aotriton.cmake) pins AOTriton `0.13b` at `6e00ef3` and includes an `amd-gfx115x` image family. | Treat PyTorch, ROCm Triton, and AOTriton as one build lane. Do not independently select Triton 3.6 or 3.7 for the PyTorch 2.13 package. |
| TorchVision | [TorchVision 0.28.0 metadata](https://pypi.org/project/torchvision/0.28.0/) requires exactly `torch==2.13.0`; it supports Python 3.10+ except 3.14.1. | Exact pair with PyTorch 2.13.0. Python 3.14.7 is inside the declared range. |
| AOTriton | [AOTriton 0.13b](https://github.com/ROCm/aotriton/releases/tag/0.13b) is a maintenance release and the exact release embedded by the PyTorch branch. | Use 0.13b as part of PyTorch, not as an independently moving optimization lane. |
| TorchAO | [TorchAO 0.18.0 release notes](https://github.com/pytorch/ao/releases/tag/v0.18.0) set the minimum PyTorch version to 2.11 and pin release CI to PyTorch 2.13. The package does not declare Torch as an install dependency because it must already exist for a source build. | Compatible candidate with PyTorch 2.13, but optional for core vLLM serving. Its compiled and Python-only surfaces still need installed smokes. |
| Transformers | [Transformers 5.15.0 metadata](https://pypi.org/project/transformers/5.15.0/) allows `torch>=2.5`, requires `safetensors>=0.8.0`, `huggingface-hub>=1.5.0,<2.0`, and `tokenizers>=0.22.0,<=0.23.0`. Its optional Torch and Mistral integrations require `accelerate>=1.1.0` and `mistral-common[image]>=1.11.7`. | PyTorch 2.13 is admitted. safetensors 0.8.0 is a hard floor. Use mistral-common 1.11.7 when retaining the repo's Mistral model surface. |
| vLLM core metadata | [vLLM 0.27.0 common requirements](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/requirements/common.txt) require `transformers>=5.5.3`, `safetensors>=0.6.2`, `mistral-common[image]>=1.11.6`, and exactly `compressed-tensors==0.17.0`. | Transformers 5.15, safetensors 0.8.0, and mistral-common 1.11.7 satisfy the combined floors. compressed-tensors must remain 0.17.0 for an unpatched vLLM 0.27 package. |
| vLLM build target | [vLLM 0.27 CMake](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/CMakeLists.txt) lists `gfx1151`, supports Python 3.10 through 3.14, and sets its expected ROCm PyTorch version to 2.13.0. Its stable libtorch extension targets the PyTorch 2.11 C shim so it remains ABI-compatible with newer PyTorch. | The source tree intends to build against PyTorch 2.13 on `gfx1151`. This is the strongest first-party evidence for the candidate serving core. |

## vLLM's ROCm release assets disagree

vLLM 0.27.0 cannot be treated as a prevalidated binary drop for this repo:

- Its [ROCm build requirements](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/requirements/build/rocm.txt)
  pin `torch==2.11.0`, `torchvision==0.26.0`, and `triton==3.6.0`, contrary
  to the same tag's CMake expectation of PyTorch 2.13.
- Its [ROCm base Dockerfile](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/docker/Dockerfile.rocm_base)
  pins ROCm PyTorch 2.11 commit `d0c8b1f3`, ROCm Triton 3.6 commit
  `0f380657`, TorchVision `v0.24.1`, and AITER `v0.1.19`.
- Its [ROCm installation guide](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/docs/getting_started/installation/gpu.rocm.inc.md)
  explicitly supports `gfx1151`, but says prebuilt ROCm wheels bundle their
  own PyTorch and may be incompatible with other PyTorch builds. The listed
  stable wheels are Python 3.12-only; Python 3.14 therefore requires a source
  build.

This conflict is not a proof that PyTorch 2.13 fails. It is a release-asset
inconsistency. The package lane must review which assets are stale, build vLLM
0.27 against the repo-owned PyTorch/Triton closure, and retain build, import,
and live-scenario gates. No metadata-only override can make that validation
claim.

## Quantization and optional integration constraints

### Compressed tensors

- vLLM 0.27 hard-pins `compressed-tensors==0.17.0` in its common
  requirements.
- [compressed-tensors 0.17.0 metadata](https://pypi.org/project/compressed-tensors/0.17.0/)
  accepts `torch>=2.10.0` and `transformers>=4.45.0`, so it admits the core.
- vLLM 0.27 contains a dedicated
  [RDNA3 W4A16 compressed-tensors MoE path](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors_moe/compressed_tensors_moe_wna16_rdna3.py).
  That is source-level relevance for `gfx1151`, not local correctness proof.
- Do not adopt compressed-tensors 0.17.1 or current 0.18.0 into the vLLM
  0.27 serving environment without an explicit vLLM metadata/source review
  and affected scenario validation.

### TorchAO

TorchAO is optional in both Transformers and vLLM. vLLM's
[TorchAO integration](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/vllm/model_executor/layers/quantization/torchao.py)
requests TorchAO only when the quantization method is selected, requires at
least 0.10.0, and has a separate code path for 0.15.0+. Transformers 5.15's
[TorchAO quantizer](https://github.com/huggingface/transformers/blob/5eddc12edfaf8cafde8c9bae4ccb12f8a139b4f9/src/transformers/quantizers/quantizer_torchao.py)
uses the current TorchAO safetensors APIs. TorchAO 0.18 is therefore a coherent
optional extension of the core, not a hard vLLM dependency.

### AITER and FlyDSL

- [AITER 0.1.19.post2](https://github.com/ROCm/aiter/releases/tag/v0.1.19.post2)
  requires exactly `flydsl==0.3.0`. Its setup logic uses Triton 3.7.0 by
  default, verifies a minimum of 3.6.0, and can preserve the installed system
  Triton with `AITER_USE_SYSTEM_TRITON=1`.
- The PyTorch 2.13 lane selects ROCm Triton 3.8.0. AITER has no declared upper
  bound, but AITER's own default and vLLM's published AITER build use older
  Triton versions. System-Triton mode is the only sensible packaging shape;
  compatibility with 3.8.0 remains a host-validation gate.
- [AITER's hardware table](https://github.com/ROCm/aiter/blob/a63ede724b153564f3ed3fc538055fd15178c77d/README.md#supported-hardware)
  classifies `gfx1151` as experimental. It says most FlyDSL and Triton kernels
  run on RDNA, while most CK and assembly kernels remain CDNA-only.
- vLLM 0.27's
  [AITER support predicate](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/vllm/_aiter_ops.py#L52-L72)
  requires ROCm plus CDNA generation greater than 2. Its
  [`get_cdna_version`](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/vllm/platforms/rocm.py#L346-L355)
  returns 0 for `gfx1151`. The general vLLM AITER path is therefore disabled
  on Strix Halo in this release even when AITER is installed.
- FlyDSL's earlier source-provenance blocker has changed. AMD now publishes
  [ROCm/FlyDSL](https://github.com/ROCm/FlyDSL) with an Apache-2.0
  [v0.3.0 source tag](https://github.com/ROCm/FlyDSL/releases/tag/v0.3.0)
  matching AITER's exact pin. The tagged
  [source build](https://github.com/ROCm/FlyDSL/blob/5675194f18f0655ce1f979c517f673533963fa93/setup.py)
  embeds an MLIR runtime and carries DLPack and TVM-FFI submodules. PyPI still
  publishes wheels but no sdist for 0.3.0.

The source tag makes FlyDSL packageable in principle, but does not make AITER
a required vLLM dependency. Refresh the existing FlyDSL investigation around
the tagged source and recursive source closure. Keep AITER experimental until
a direct installed JIT smoke passes and a chosen vLLM path demonstrably uses
it on `gfx1151`.

### llmcompressor, AutoRound, and Accelerate

The current released authoring-tool lane cannot share the serving core:

- [llmcompressor 0.12.0.1](https://pypi.org/project/llmcompressor/0.12.0.1/)
  requires `torch>=2.10.0,<=2.12.0`,
  `transformers>=5.9.0,<=5.10.1`,
  `auto-round>=0.10.2,<=0.13.0`,
  `accelerate>=1.6.0,<=1.13.0`, and exactly
  `compressed-tensors==0.17.1`.
- Those caps conflict with PyTorch 2.13, Transformers 5.15, AutoRound 0.13.1
  or newer, Accelerate 1.14.0, and vLLM's exact compressed-tensors 0.17.0.
- [AutoRound 0.14.2](https://pypi.org/project/auto-round/0.14.2/) and
  [Accelerate 1.14.0](https://pypi.org/project/accelerate/1.14.0/) have broad
  direct Torch/Transformers constraints and can be evaluated independently.
  They do not repair llmcompressor's upper bounds.

Keep llmcompressor out of the core environment. Reopen it only for a newer
release whose declared constraints admit the serving versions, or for an
explicitly isolated authoring environment with its own package and validation
contract.

### AMD Quark

vLLM 0.27's [ROCm requirements](https://github.com/vllm-project/vllm/blob/4bdc8a788d2e2ce9165d552b3d4d8b72604626bf/requirements/rocm.txt)
list exactly `amd-quark==0.12.post1`, although the adjacent comment limits its
purpose to Quark quantization. [AMD Quark 0.12.post1 metadata](https://pypi.org/project/amd-quark/0.12.post1/)
requires Python 3.11 through 3.13 and publishes only a wheel. It is therefore
incompatible with the repo's Python 3.14 runtime.

vLLM's Quark checkpoint reader does not import the AMD Quark authoring package.
Preserve the repo's explicit omission of `amd-quark` from the serving runtime;
validate Quark-exported checkpoint consumption separately. Treat the upstream
ROCm requirements entry as a deliberate package-metadata divergence that must
remain documented.

## Candidate package boundary

### Required serving core

| Package surface | Candidate constraint |
| --- | --- |
| ROCm PyTorch | 2.13.0 at a reviewed `release/2.13` commit |
| ROCm Triton | PyTorch's reviewed 3.8.0 commit pin |
| AOTriton | 0.13b / `6e00ef3` as selected by PyTorch |
| TorchVision | 0.28.0 exactly |
| vLLM | 0.27.0 source build; reconcile its conflicting ROCm build assets |
| Transformers | 5.15.0 |
| tokenizers | 0.22.0 through 0.23.0 |
| huggingface-hub | 1.5.0 through the latest release below 2.0 |
| safetensors | 0.8.0 |
| mistral-common | 1.11.7 |
| compressed-tensors | 0.17.0 exactly |

### Optional, separately gated

| Package surface | Disposition |
| --- | --- |
| TorchAO 0.18.0 | Compatible optional integration; retain installed API and selected quantization scenario gates. |
| AITER 0.1.19.post2 | Experimental on `gfx1151`; general vLLM AITER selection is disabled in vLLM 0.27. Do not make it a core dependency. |
| FlyDSL 0.3.0 | Exact AITER dependency now has tagged source. Package-source closure and embedded MLIR validation remain separate work. |
| AutoRound 0.14.2 | Optional authoring tool; evaluate outside llmcompressor's current caps. |
| Accelerate 1.14.0 | Optional runtime/authoring helper; compatible on its own. |
| Quark/AWQ/GPTQ/bitsandbytes scenarios | Consumer scenarios remain optional. A format listed by vLLM is not evidence that an authoring package belongs in the serving environment. |

### Blocked or excluded from the serving core

| Package surface | Reason |
| --- | --- |
| llmcompressor 0.12.0.1 | Hard upper bounds conflict with PyTorch, Transformers, AutoRound, and Accelerate; exact compressed-tensors pin conflicts with vLLM. |
| compressed-tensors 0.17.1 or 0.18.0 | vLLM 0.27 requires exactly 0.17.0. |
| amd-quark 0.12.post1 | Requires Python below 3.14 and is not needed to consume already-exported Quark checkpoints in vLLM. |
| vLLM ROCm wheel route | No stable vLLM 0.27 ROCm wheel is listed. The published ROCm wheel route is Python 3.12-only and bundles a validated PyTorch closure different from the repo-owned one. |

## Execution gates implied by this research

No package, host, or live-test action was performed. A later implementation
plan should preserve these gates:

1. Freeze one reviewed `release/2.13` PyTorch commit together with its exact
   ROCm Triton and AOTriton pins.
2. Build and install PyTorch, AOTriton, Triton, and TorchVision as one ABI lane;
   run imports plus a bounded ROCm tensor smoke.
3. Reconcile vLLM 0.27's CMake intent with its stale/conflicting ROCm build
   requirements and Docker pins; record every local metadata divergence.
4. Build vLLM from source against the installed core and run extension import,
   unquantized `gfx1151` generation, and compressed-tensors RDNA scenario gates.
5. Add TorchAO only after its installed API/safetensors smoke and a selected
   vLLM or Transformers consumer scenario pass.
6. Keep AITER off the required path. If pursued, first package FlyDSL from its
   tagged recursive source closure, preserve system Triton 3.8, run AITER JIT
   smokes, and prove a concrete `gfx1151` consumer despite vLLM's CDNA gate.
7. Do not install llmcompressor or AMD Quark into the core to satisfy metadata.
   Track them as separate blocked or isolated tooling decisions.

## Source disposition

All sources below were retrieved on 2026-08-11. No local result was promoted.

| Source | Type and exact ref | Extracted value | Status | Affected tracked work |
| --- | --- | --- | --- | --- |
| [ROCm PyTorch](https://github.com/ROCm/pytorch/commit/4be323cffdd92aeb272b15958ebafe9a5e6c6a33) | First-party source, `release/2.13` head `4be323c` | PyTorch, ROCm Triton, AOTriton, and `gfx115x` source/build contract | `requires-host-validation` | Runtime-base refresh; no tracked failure state changed |
| [TorchVision 0.28.0](https://pypi.org/project/torchvision/0.28.0/) | Maintainer-published package metadata and upstream tag `v0.28.0` | Exact PyTorch pair and Python range | `planned` | Runtime-base refresh |
| [AOTriton 0.13b](https://github.com/ROCm/aotriton/releases/tag/0.13b) | First-party release/tag `0.13b`, commit `6e00ef3` | PyTorch-embedded attention runtime and `gfx115x` image family | `requires-host-validation` | Runtime-base refresh |
| [TorchAO 0.18.0](https://github.com/pytorch/ao/releases/tag/v0.18.0) | First-party release/tag `v0.18.0`, commit `5f2baf9` | PyTorch 2.13 compatibility and optional quantization APIs | `requires-host-validation` | Optional TorchAO scenarios; no failure state changed |
| [vLLM 0.27.0](https://github.com/vllm-project/vllm/releases/tag/v0.27.0) | First-party release/tag `v0.27.0`, commit `4bdc8a7` | `gfx1151` source support, PyTorch 2.13 CMake expectation, dependency pins, and contradictory ROCm build assets | `requires-host-validation` | Runtime refresh and all retained vLLM scenarios |
| [Transformers 5.15.0](https://github.com/huggingface/transformers/releases/tag/v5.15.0) | First-party release/tag `v5.15.0`, commit `5eddc12` | Torch, safetensors, tokenizers, Hub, Mistral, and TorchAO integration constraints | `requires-host-validation` | Model-surface refresh and retained vLLM scenarios |
| [AITER 0.1.19.post2](https://github.com/ROCm/aiter/releases/tag/v0.1.19.post2) | First-party release/tag `v0.1.19.post2`, commit `a63ede7` | Experimental `gfx1151`, FlyDSL 0.3.0, and Triton constraints | `requires-host-validation` | AITER/FlyDSL investigation; no vLLM blocker is cleared |
| [FlyDSL 0.3.0](https://github.com/ROCm/FlyDSL/releases/tag/v0.3.0) | First-party release/tag `v0.3.0`, commit `5675194` | Tagged Apache-2.0 source, embedded MLIR build, and recursive source closure | `planned` | Refresh the FlyDSL source-packageability investigation |
| [Python package release metadata](https://pypi.org/) for compressed-tensors, llmcompressor, AutoRound, Accelerate, safetensors, mistral-common, and AMD Quark | Maintainer-published registry metadata at the versions cited above | Exact dependency intersections and conflicts | `advisory-only` until packaged and tested | Quantization/tooling refresh; no tracked failure state changed |

Future sessions should recheck every moving branch and registry version before
mutation. The exact-version constraints attached to vLLM, Transformers,
llmcompressor, and AITER are the durable decision inputs; the observed latest
versions are rolling cursors.
