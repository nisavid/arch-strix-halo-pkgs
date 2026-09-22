# Generation C Version Line

Retrieved: 2026-09-22

Tickets: [#105](https://github.com/nisavid/arch-strix-halo-pkgs/issues/105)
(source and dependency freeze). Execution issues:
[#108](https://github.com/nisavid/arch-strix-halo-pkgs/issues/108) (W1
foundation F),
[#109](https://github.com/nisavid/arch-strix-halo-pkgs/issues/109) (W2A
compiler and PyTorch foundation),
[#110](https://github.com/nisavid/arch-strix-halo-pkgs/issues/110) (W2A model
dependency closure),
[#111](https://github.com/nisavid/arch-strix-halo-pkgs/issues/111)
(TorchVision and vLLM), and the nonblocking lanes
[#118](https://github.com/nisavid/arch-strix-halo-pkgs/issues/118) through
[#121](https://github.com/nisavid/arch-strix-halo-pkgs/issues/121).

Freeze input: the 2026-09-22 freshness sweep, a cache-aware
`tools/check_package_updates.py --fail-on actionable` run that started at
19:56:39Z. Under decision X7, this one sweep freezes C's version universe.

Observation rule: every selection below was observed by the sweep, or is bound
to an observed family, and was published before the sweep. Some selections are
older than the sweep's latest where that keeps the line coherent. Bindings used:

- MIGraphX 2.16.1 (`2487b688`) is bound to TheRock: the sweep observed TheRock
  7.14.1, and the MIGraphX CHANGELOG at that commit reads "MIGraphX 2.16.1 for
  ROCm 7.14.1". No freshness family tracks MIGraphX directly.
- huggingface-hub 1.32.0, pydantic 2.13.5, protobuf 36.1 and abseil-cpp
  20260817.0 are Arch packages that are not repo-owned. Each is bound to the
  repo family that consumes it and was built by Arch before the sweep.

Supersedes the candidate line in the 2026-08-11 research
([rocm-runtime-compatibility.md](rocm-runtime-compatibility.md),
[therock-python-foundation.md](therock-python-foundation.md),
[triton-flydsl-closure.md](triton-flydsl-closure.md)): ROCm PyTorch 2.13,
Triton 3.8.0 `4cff872`, AOTriton 0.13b, TorchVision 0.28, vLLM 0.27,
Transformers 5.15, compressed-tensors 0.17.0 and mistral-common 1.11.7.

Verification: three adversarial read-only checks (hard pins and pairings,
buildability, and the freeze lens) each returned "not refuted". This record
includes their corrections. No package in the line was built, installed or run
for this record, except `python-pydantic-core-gfx1151` 2.46.5, which was built
(not installed) as a hazard fix.

## Question

Inside the frozen universe, which single version line for generation C is
coherent? C consists of:

- foundation F: CPython 3.14.x, the full TheRock 7.14.x family and MIGraphX
  2.16;
- the PyTorch/vLLM closure that serves offline text, OpenAI serving,
  embeddings and reranking on `gfx1151`;
- all of it built from repo recipes.

What does the W1 (#108) build plan look like for that line?

## Decision gist

Select this line:

- **Foundation:** CPython 3.14.7, TheRock 7.14.1 (`f51dc6c9`; ai-notes
  cursor `dbfb70ef`), MIGraphX 2.16.1 (`2487b688`).
- **PyTorch lane:** ROCm PyTorch **2.12.0** at `release/2.12`
  `13da0862` (the head the sweep observed), ROCm Triton **3.8.0** at
  `669b31ac` (that commit's own pin), AOTriton **0.13b**, TorchVision
  **0.27.1**.
- **vLLM:** **0.30.0** (`ced6857`), with Transformers **5.16.1**, tokenizers
  0.23.2, safetensors 0.8.0, compressed-tensors **0.17.0**,
  mistral-common **1.11.7**, NumPy 2.5.3 (fallback 2.4.6), and pydantic-core
  2.46.5 paired with Arch pydantic 2.13.5.

The line keeps the tracked PyTorch branch (`release/2.12`). These first-party
declarations support it:

- The TheRock 7.14.1 release matrix builds PyTorch `release/2.10` through
  `release/2.12`, and takes Triton from the PyTorch commit's own pin.
- The ROCm 7.14.1 AI-ecosystem table lists PyTorch 2.12.0.
- AMD's first-party wheel index publishes `torch-2.12.0+rocm7.14.1`, which
  requires `triton==3.8.0+git4cff872c.rocm7.14.1`. That is AMD's own pairing
  of torch 2.12 with Triton 3.8.x on TheRock 7.14.1.
- vLLM 0.30.0's ROCm 7.14 build assets pin `torch==2.12.0+rocm7.14.0`
  (`requirements/build/rocm.txt`), and `Dockerfile.rocm_base` builds
  ROCm/pytorch `release/2.12`. Those assets pair torch 2.12 with Triton
  **3.7.1** (`0263a6a6`), not 3.8.

vLLM 0.30.0 still declares ROCm torch 2.13 in CMake (warning only) and
`torch == 2.13.0` as its CUDA build pin. That is the same kind of release-asset
inconsistency that vLLM 0.27 had. Build and live gates resolve it, not a
metadata override (see
[Upstream inconsistencies](#upstream-inconsistencies-and-their-gates)).

Keep PyTorch 2.14 (with TorchVision 0.29, the scikit-build-core rewrite and a
vLLM release that targets 2.14) as the next PyTorch lane after closeout. X7
routes later drift to post-closeout maintenance
([#147](https://github.com/nisavid/arch-strix-halo-pkgs/issues/147)).

This is a compatibility decision, not validation evidence. No first-party
build covers the exact combination of Python 3.14, torch 2.12 `13da0862`,
Triton 3.8.0 `669b31ac`, and vLLM 0.30 on `gfx1151`. The planned build and
live gates are what validate it.

## Selected line

| Surface | Selection | Exact ref | Sweep observation | Binding first-party constraint |
| --- | --- | --- | --- | --- |
| CPython | 3.14.7 | [`Python-3.14.7.tar.xz`](https://www.python.org/ftp/python/3.14.7/) | Arch `python` 3.14.7-1 (primary), cpython 3.14.7 | vLLM `<3.15`; TorchVision excludes only 3.14.1; NumPy 2.5 `>=3.12` |
| TheRock | 7.14.1 | tag [`therock-7.14.1`](https://github.com/ROCm/TheRock/releases/tag/therock-7.14.1) (tag object `5514fb2f`) = `f51dc6c91e0d3214f22853fd5cb3f96dbc7d2c4b`; payload `therock-dist-linux-gfx1151-7.14.1.tar.gz` from the [multi-arch tarball index](https://repo.amd.com/rocm/tarball-multi-arch/) | `7.14.1` (TheRock 10.0 was masked; see [Open risks](#open-risks)) | PyTorch release matrix `release/2.10`–`2.12` ([matrix](https://github.com/ROCm/TheRock/blob/f51dc6c91e0d3214f22853fd5cb3f96dbc7d2c4b/build_tools/github_actions/configure_pytorch_release_matrix.py)) |
| ai-notes cursor | `dbfb70ef` | `dbfb70efc26fccf6ab2b00ee60ff0c96d37d37b0` | submodule head | Provenance stamp only; no TheRock impact |
| MIGraphX | 2.16.1 | AMDMIGraphX `release/rocm-rel-7.14` head [`2487b688`](https://github.com/ROCm/AMDMIGraphX/commit/2487b688c453b9007ac69ff1d79ad6cf9b509901) (2026-09-01, untagged) = tag `rocm-7.14` (`4bcfe75b`, 2.16.0) + one MLIR-literal fix + the 2.16.1 version bump | bound to the TheRock family | CHANGELOG marks 2.16.1 for ROCm 7.14.1. AMD validates 2.16 only on gfx942/gfx950 with Python 3.12 |
| ROCm PyTorch | 2.12.0 | ROCm/pytorch `release/2.12` [`13da0862`](https://github.com/ROCm/pytorch/commit/13da08625e0d25586351146b4c444f5263997ef8) | `13da0862` (branch head, committed 19:53:51Z) | TheRock 7.14.1 matrix; ROCm 7.14.1 table lists PyTorch 2.12.0 |
| ROCm Triton | 3.8.0 | ROCm/triton `release/internal/3.8.x` [`669b31ac`](https://github.com/ROCm/triton/commit/669b31acc1dd1b3fd93286afd5db67f65d9f7557) | `669b31ac` (branch head) | Exact pin in [`13da0862` `triton.txt`](https://github.com/ROCm/pytorch/blob/13da08625e0d25586351146b4c444f5263997ef8/.ci/docker/ci_commit_pins/triton.txt). See [Triton provenance](#triton-provenance) |
| AOTriton | 0.13b | tag [`0.13b`](https://github.com/ROCm/aotriton/releases/tag/0.13b) = `6e00ef3e`; vendored Triton `db82b800` (unchanged from 0.12b) | release 0.14b; Arch 0.13b-2 | `13da0862` [`aotriton.cmake`](https://github.com/ROCm/pytorch/blob/13da08625e0d25586351146b4c444f5263997ef8/cmake/External/aotriton.cmake) accepts API `>=0.12,<0.14` |
| TorchVision | 0.27.1 | [`v0.27.1`](https://github.com/pytorch/vision/compare/v0.27.0...v0.27.1) (identical to 0.27.0 except `version.txt`) | 0.29.0 | ROCm `related_commits` pairs `release/2.12` with vision `release/0.27` (fork commit `b3d5b111`); vLLM `Dockerfile.rocm_base` builds v0.27.1 on ROCm `release/2.12` |
| vLLM | 0.30.0 | tag `v0.30.0` = `ced6857afa0ea7b2e3f0846a62e1394e90f15607` | 0.30.0 | [common.txt](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/requirements/common.txt), [CMakeLists.txt](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/CMakeLists.txt) |
| Transformers | 5.16.1 | [PyPI 5.16.1](https://pypi.org/project/transformers/5.16.1/) | 5.17.0 | vLLM `>=5.10.4`. vLLM 0.30 CI lock pins 5.16.1 ([test/rocm.txt](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/requirements/test/rocm.txt)) |
| tokenizers | 0.23.2 | [PyPI 0.23.2](https://pypi.org/project/tokenizers/0.23.2/) | 0.23.2 | Transformers 5.16.1 `>=0.23.1,<0.24.0` |
| safetensors | 0.8.0 | [PyPI 0.8.0](https://pypi.org/project/safetensors/0.8.0/) | 0.8.0 | Transformers 5.16.1 `>=0.8.0` |
| compressed-tensors | 0.17.0 | [PyPI 0.17.0](https://pypi.org/project/compressed-tensors/0.17.0/) | 0.19.0 | vLLM 0.28–0.30 `compressed-tensors == 0.17.0` |
| mistral-common | 1.11.7 | [PyPI 1.11.7](https://pypi.org/project/mistral-common/1.11.7/) | 1.12.0 | vLLM `[image]>=1.11.6`; Transformers mistral extra `>=1.11.7`; Python `<3.15`; needs `pydantic-extra-types[pycountry]`. 1.12.0 is rejected, see [Not selected](#not-selected-from-the-frozen-universe) |
| NumPy | 2.5.3 (fallback 2.4.6) | [PyPI 2.5.3](https://pypi.org/project/numpy/2.5.3/) | 2.5.3; Arch 2.5.3-1 | Python `>=3.12`. Two caps are documented divergences; see [NumPy caps](#numpy-caps) |
| pydantic-core | 2.46.5 | PyPI sdist `pydantic_core-2.46.5.tar.gz`, the same release as Arch `python-pydantic-core` 2.46.5-1 | Arch 2.46.5-1 (primary); PyPI 2.49.0 | Arch/PyPI pydantic 2.13.5 requires `pydantic-core==2.46.5` ([PyPI](https://pypi.org/project/pydantic/2.13.5/)) |
| Accelerate | 1.15.0, kept | [PyPI 1.15.0](https://pypi.org/project/accelerate/1.15.0/) | 1.15.0 | Not required by vLLM or Transformers core. Kept because it is cheap pure Python |
| huggingface-hub (Arch, not repo-owned) | 1.32.0 | Arch `python-huggingface-hub` | not tracked; bound to Transformers and vLLM | vLLM 0.30 `>=1.31.0`; Transformers `<2.0`. Hub 1.31 and later declare `click>=8.4.2,<9`, while Arch `python-click` is 8.3.3. Only `huggingface_hub/cli/*` imports click, so library paths are unaffected; a `pip check`-style audit will flag it |
| prometheus-fastapi-instrumentator (not repo-owned) | 7.0.0, divergence | the host's AUR/local 7.0.0-2 | not tracked | vLLM 0.30 `>=8.0.0`. See [prometheus-fastapi-instrumentator](#prometheus-fastapi-instrumentator-divergence) |

Other sweep families that are hard runtime dependencies of the selected vLLM
or Transformers. Each is selected at the version the sweep observed:

| Family | Selection | Why it is in the line |
| --- | --- | --- |
| aiohttp | 3.14.3 | vLLM `aiohttp>=3.13.3`; needs `multidict<7`, `yarl<2`, `frozenlist>=1.1.1` ([PyPI](https://pypi.org/project/aiohttp/3.14.3/)) |
| multidict / yarl / frozenlist | 6.9.1 / 1.25.1 / 1.8.0 (current) | aiohttp closure; yarl 1.25.1 needs `multidict>=4.0`, `propcache>=0.2.1` |
| sentencepiece | 0.2.2 | vLLM `sentencepiece` (unversioned) |
| pillow | 12.3.0 | vLLM `pillow`; TorchVision `>=5.3,!=8.3.*`; mistral-common `>=10.3` |
| watchfiles | 1.3.0 | vLLM `watchfiles`; uvicorn[standard] |
| uvloop / httptools | 0.22.1 / 0.8.0 (current) | fastapi[standard] → uvicorn[standard] |
| msgspec / pyyaml / psutil / openai-harmony | 0.21.1 / 6.0.3 / 7.2.2 / 0.0.8 (current) | direct vLLM requirements; Transformers needs `pyyaml>=5.1` |

Repo packages coupled to the PyTorch ABI but outside the four required
outcomes. They are listed here only because they must be rebuilt against the
selected PyTorch, or held off the activation transaction:

| Family | Selection | Note |
| --- | --- | --- |
| torch_migraphx | master `5afb9ffd` (the sweep head) | Includes upstream "Fix import for torch>=2.12: quantize_pt2e removed" ([compare](https://github.com/ROCm/torch_migraphx/compare/b94b985586a051fbee19aefe8c934bb7c1a9df0a...5afb9ffdd7f5489727bdfbb323f1b2584e3676c2)). Re-derive local patch 0001 against it, and keep local patch 0003 (NumPy cap relaxation) through the rebase |
| flash_attention | `main_perf` `3f94643f` (unchanged) | Rebuild against the new PyTorch. The package depends on the repo AITER package, which is a W5 removal default (see [W5 removals](#w5-transaction-removals)) |
| torchao | 0.18.0, optional | Minimum PyTorch 2.11 ([v0.18.0](https://github.com/pytorch/ao/releases/tag/v0.18.0)). The repo's torch-migraphx package depends on it |

## ROCm PyTorch branch adjudication

The PyTorch lane preferred 2.12 and the vLLM lane preferred 2.13 (it accepted
2.12). The first-party declarations settle the choice:

| Declaration (pinned source) | 2.12 `13da0862` | 2.13 `9647b024` | 2.14 `151661a6` |
| --- | --- | --- | --- |
| Observed by the 2026-09-22 sweep | yes (tracked branch head) | no (head predates the sweep, but no check watches that branch) | Arch baseline 2.14.0-1 only |
| TheRock 7.14.1 builds it ([matrix](https://github.com/ROCm/TheRock/blob/f51dc6c91e0d3214f22853fd5cb3f96dbc7d2c4b/build_tools/github_actions/configure_pytorch_release_matrix.py)) | yes | no | no |
| ROCm 7.14.1 AI-ecosystem table ([notes](https://rocm.docs.amd.com/en/docs-7.14.1/about/release-notes.html)) | PyTorch 2.12.0 | not listed | not listed |
| AMD first-party wheels ([index](https://repo.amd.com/rocm/whl-multi-arch/)) | `torch-2.12.0+rocm7.14.1` (Triton 3.8.0 `4cff872c`) and `+rocm7.14.0` (Triton 3.7.1 `0263a6a6`) | `torch-2.13.0+rocm7.14.0` for cp310–cp314 (published 2026-09-03; `git_version 4be323cf`, 23 commits behind the `release/2.13` head; Triton 3.8.0 `4cff872c`). No `rocm7.14.1` build | none on 7.14 |
| Upstream PyTorch ROCm binaries | via TheRock | v2.13.0 ships only rocm7.1 and rocm7.2 | v2.14.0 ships rocm7.2 and rocm7.14 |
| vLLM 0.30.0 ROCm 7.14 build assets ([build/rocm.txt](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/requirements/build/rocm.txt), [rocm_base](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/docker/Dockerfile.rocm_base)) | `torch==2.12.0+rocm7.14.0`; `release/2.12` `6bbd260`; Triton 3.7.1 | none | none |
| vLLM 0.30.0 CMake `TORCH_SUPPORTED_VERSION_ROCM "2.13.0"` ([L72](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/CMakeLists.txt#L72), [L205-L209](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/CMakeLists.txt#L205-L209)) | `WARNING` only | matches | at or above the minimum; the 2.13-only hotfix does not apply |
| vLLM 0.30.0 `pyproject.toml` build-system `torch == 2.13.0` (CUDA build pin) | not enforced: the package builds with `pip wheel --no-build-isolation`, and ROCm wheel metadata comes from `requirements/rocm.txt`, which has no torch pin | matches | not enforced |
| vLLM 0.30.0 Python gates above 2.12 | one: `donate_graph_module` in `standalone_compile` is skipped below 2.13 ([compiler_interface.py L320](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/vllm/compilation/compiler_interface.py#L320)) | all gates pass | untested; private `torch._inductor` APIs change every minor release |
| TorchVision pair | 0.27.x | 0.28.0 | 0.29.0 |
| ASHP patch carry (dry run) | drop 0009, rebase 0005 | drop 0002 and 0009, rebase 0004 and 0005 | drop 0002, 0006 and 0009, rebase 0004 and 0005, rewrite 0001 and the wheel flow for scikit-build-core |

Result: 2.12.

- **2.13 is rejected only under the X7 observation rule.** The sweep did not
  observe the `release/2.13` head, so selecting it would need an X7
  exception. A ROCm 7.14 pairing does exist: AMD's first-party index
  publishes `torch-2.13.0+rocm7.14.0`. That index has no `rocm7.14.1` build
  of 2.13, and TheRock 7.14.1's matrix stops at 2.12, but neither fact is the
  ground for the rejection.
- **2.14 is rejected** because no vLLM release in the universe pairs with it,
  and it needs a build-system rewrite.

2.12 also minimises ABI churn for installed torch consumers:

- The host generation is already 2.12.0 at `c7badbdf`.
- ROCm's own `related_commits` pairs `release/2.12` with torchaudio
  `release/2.11`, and the host's AUR torchaudio is 2.11.0.

Upstream PyTorch v2.12.1 adds only five commits over v2.12.0: CD matrix
changes, an MPS fix, a version bump and an NVIDIA Triton bump
([compare](https://github.com/pytorch/pytorch/compare/v2.12.0...v2.12.1)).
None of them matter for ROCm, which is why ROCm `release/2.12` still reports
2.12.0.

## Triton provenance

- TheRock 7.14.1 shipped its torch 2.12 wheel with Triton `4cff872c`. That was
  the `release/2.12` `triton.txt` pin from 2026-07-22 (ROCm/pytorch
  `ae820be2`).
- The pin moved to `669b31ac` on 2026-09-10 (ROCm/pytorch `d6c79fda`).
  `669b31ac` is 24 commits ahead of `4cff872c` on the same branch, with no
  divergence ([compare](https://github.com/ROCm/triton/compare/4cff872ced001ea92d9fcf05b3f6517e2b486d19...669b31acc1dd1b3fd93286afd5db67f65d9f7557)).
  One of those commits, `a287841c`, re-pins LLVM.
- The selected pair (`13da0862` with `669b31ac`) is internally consistent, but
  AMD has not built it. Only the build and live gates validate it.
- vLLM's `docker/Dockerfile.rock_base` at `ced6857` runs torch
  `2.12.0+rocm10.0.0` with Triton `3.8.0+git4cff872c.rocm10.0.0`. That is a
  ROCm 10.0 pairing with `4cff872c`, not a 7.14 pairing with `669b31ac`, so it
  is not 7.14 evidence.
- vLLM 0.30 has an open, unmerged port of its Triton kernels to Triton 3.8:
  [vllm#50605](https://github.com/vllm-project/vllm/pull/50605) ("[ROCm] Bump
  torch 2.13, triton 3.8"). It edits kernels for Kimi-K3, MiniMax-M3,
  Inkling, mxfp8 and gpt-oss MoE. None of them is on the four required
  outcomes, and the PR does not touch the generic `TRITON_ATTN` or
  unified-attention path. It is the known-incompatibility reference for this
  pairing. The Gemma 4 `TRITON_ATTN` live gate covers the residual risk.

## Upstream inconsistencies and their gates

| Inconsistency | Resolution in C | Gate that resolves it |
| --- | --- | --- |
| vLLM 0.30.0 CMake expects ROCm torch ≥ 2.13.0 and pyproject pins `torch == 2.13.0`, but its own ROCm build assets pin torch 2.12.0 (the same pattern as vLLM 0.27, whose CMake said 2.13 while `build/rocm.txt` said 2.11) | Build against ROCm PyTorch 2.12.0. Record the divergence in the vLLM recipe | The vLLM build log shows only the CMake warning (no error) and skips the 2.13-only `pytorch_stable_string` hotfix. Extension import and `vllm --version` smokes pass. Offline text, OpenAI serving, embeddings and reranking pass live on `gfx1151` |
| vLLM 0.30.0 `requirements/rocm.txt` and `requirements/build/rocm.txt` pin ROCm Triton 3.7.1 (`0263a6a6`), while the selected PyTorch commit pins 3.8.0 `669b31ac` | Follow the PyTorch commit pin, as TheRock does. See [Triton provenance](#triton-provenance) and vllm#50605 | PyTorch Inductor/Triton smoke; Gemma 4 `TRITON_ATTN` decode correctness (vLLM issue [#57493](https://github.com/vllm-project/vllm/issues/57493) shows `ROCM_ATTN` greedy nondeterminism on `gfx1151`) |
| The `13da0862` in-tree AOTriton pin is 0.13.50tp, a pre-release that adds only gfx1250 tuning | Build against system AOTriton 0.13b, which is inside the declared API range `>=0.12,<0.14` | The PyTorch configure log accepts system AOTriton 0.13b. SDPA flash and mem-efficient smoke on `gfx1151` |
| TorchVision 0.27.1 PyPI metadata pins `torch==2.12.1` (the upstream release-build environment); ROCm `release/2.12` reports 2.12.0 | The code is identical to 0.27.0. A source build derives the torch requirement from the build environment | TorchVision import and ops smoke against the installed PyTorch |
| vLLM `compressed-tensors == 0.17.0`, but the sweep latest is 0.19.0 | 0.17.0 | Compressed-tensors RDNA scenario, if retained |
| vLLM metadata caps that the repo does not satisfy: `fastapi<0.137` (Arch 0.141.1), `setuptools<81` (Arch 84), `numba==0.65.0` (needs `numpy<2.5`), `amd-quark==0.12.post1` (Python `<3.14`), `mcp>=2` (Arch 1.29, lazy), `prometheus-fastapi-instrumentator>=8.0.0` (host 7.0.0), `lark==1.2.2`, `outlines_core==0.2.14`, `depyf==0.20.0`, `llguidance` 1.7.x (lazy) | Documented divergences, as in the current recipe. Keep the optional-SageMaker carry so that `model_hosting_container_standards` stays optional. Every quark import in vLLM is function-local | OpenAI server starts; import smoke of every top-level import; the `/metrics` gate below |
| Transformers 5.17.0 metadata admits vLLM 0.30.0, but the v0.30.0 [`pixtral.py`](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/vllm/model_executor/models/pixtral.py#L19-L22) imports symbols that 5.17 removed. The fix, [vllm#56108](https://github.com/vllm-project/vllm/pull/56108), landed after the tag | Select 5.16.1, the version vLLM 0.30 CI tested | None needed for 5.16.1 |

### NumPy caps

Two packages in C declare NumPy caps that 2.5.3 does not satisfy:

- **numba 0.65.0.** vLLM 0.30 `requirements/rocm.txt` pins `numba==0.65.0`,
  whose PyPI metadata requires `numpy<2.5`. This is a documented divergence.
  The vLLM PKGBUILD does not depend on numba. Every numba import on the
  required path is lazy: `ngram_proposer` is imported under `TYPE_CHECKING` or
  inside functions, the Inkling processor is lazy, and `jit_monitor` imports
  numba inside a context manager. Host Arch numba 0.67.0 admits `numpy<2.6`.
- **torch_migraphx `5afb9ffd`** caps `numpy<2.0` in `setup.py` and
  `requirements.txt`. The existing local patch 0003 relaxes that cap. Keep it
  through the rebase onto `5afb9ffd`.

The fallback is the current NumPy 2.4.6. The torch, TorchVision and vLLM NumPy
interop smokes decide between them.

### prometheus-fastapi-instrumentator divergence

vLLM 0.30 `common.txt` requires `prometheus-fastapi-instrumentator>=8.0.0`
("v8 unblocks starlette >= 1.0"). C keeps the host's AUR/local 7.0.0-2 and
records it as a divergence:

- The AUR head is still 7.0.0. Its metadata declares
  `starlette>=0.30.0,<1.0.0`, and Arch starlette is 1.6.0.
- 7.0.0 has `routing._get_route_name`, the function vLLM 0.30 monkeypatches
  (`vllm/entrypoints/serve/instrumentator/metrics.py`). vLLM's own
  `_patch_instrumentator_route_walk` tolerates path-less FastAPI routes, so a
  structural break is unlikely.
- Its 8.0.1 release fixes an `AttributeError` on every request for
  `include_router()` routers on FastAPI 0.116 and newer
  ([releases](https://github.com/trallnag/prometheus-fastapi-instrumentator/releases)).
  The host runs FastAPI 0.141.1.
- PyPI 8.1.0 was published 2026-07-26, before the sweep, but no freshness
  family tracks it, so selecting it would stretch the observation rule.

Gate (W6): OpenAI serving answers requests, and `GET /metrics` returns
Prometheus text, with 7.0.0 installed. If the gate fails, package 8.x.

## Hard constraints

### Foundation F

| Component | Constraint (pinned source) | Result |
| --- | --- | --- |
| TheRock | `therock-7.14.1` = `f51dc6c9`, the `release/therock-7.14` head. It adds six commits over 7.14.0: an LLVM revert for amdflang, RCCL instrumentation, and a meta-package dependency fix ([compare](https://github.com/ROCm/TheRock/compare/therock-7.14...therock-7.14.1)) | Stage the gfx1151 dist tarball (1,713,467,716 bytes, published 2026-08-31). Record its sha256 at fetch |
| TheRock payload shape | `KPACK_SPLIT_ARTIFACTS` defaults to ON ([FLAGS.cmake](https://github.com/ROCm/TheRock/blob/f51dc6c91e0d3214f22853fd5cb3f96dbc7d2c4b/FLAGS.cmake)). For 7.14.x, the gfx1151 tarball is published only under `tarball-multi-arch/`. The policy ignores `opt/rocm/.kpack/**` | Before rendering, check for `.rocm_kpack_ref` sections and inventory `.kpack/` |
| MIGraphX | `2487b688` = `rocm-7.14` + [#5223](https://github.com/ROCm/AMDMIGraphX/commit/3bff2e6774) (`prepare_mlir.cpp`) + the version bump. The repo builds with MLIR OFF | Pin 2.16.1. The no-MLIR stub patch must drop its `RockEnums.h` replacement, which upstream #4962 already made, and keep the four stubs |
| Protobuf/Abseil for the MIGraphX parsers | Arch extra now has protobuf 36.1 and abseil-cpp 20260817.0. The host still has 35.1 and 20260526, pinned by installed `migraphx-gfx1151` 7.13.0-3 (`libprotobuf.so=35.1.0-64`) | Build against 36.1 in an isolated prefix. Derive SONAMEs at build time |
| CPython | 3.14.7. `python-gfx1151` carries no source patches. Arch 3.14.7-1 adds the cpython `927eb448` POSIX-2024 backport ([Arch commit](https://gitlab.archlinux.org/archlinux/packaging/packages/python/-/commit/3254b07)) | Version, checksum and path bump. Carrying the backport is an Arch-parity decision |

### PyTorch lane

| Component | Constraint (pinned source) | Result |
| --- | --- | --- |
| ROCm PyTorch `13da0862` | `version.txt` 2.12.0; Triton pin `669b31ac`; AOTriton API `>=0.12,<0.14`; Python 3.14 classifier; gfx1151 in the hipBLASLt and CK WMMA lists, but not in the CK GEMM backend gate | Keep the `release/2.12` policy branch. Move `recorded` `c7badbdf` → `13da0862`. Keep patch 0005 |
| ROCm Triton `669b31ac` | `__version__ = '3.8.0'`, "[release 3.8] Release Triton to pypi". `setup.py` supports Python 3.10–3.14. The AMD backend handles `gfx115*` explicitly. Its [`cmake/llvm-info.json`](https://github.com/ROCm/triton/blob/669b31acc1dd1b3fd93286afd5db67f65d9f7557/cmake/llvm-info.json) pins upstream LLVM `5f07f818` | The package moves off `main_perf` `0ec280cf` (3.0.0-era) onto `release/internal/3.8.x`. Re-derive the local carry and the LLVM input |
| AOTriton 0.13b | Arch `python-aotriton` 0.13b-2 builds on Python 3.14 with gfx1151 in `AOTRITON_TARGET_ARCH`. Its vendored Triton is unchanged from 0.12b | The repo's Python 3.14 cherry-pick still applies. 0.13's code-generator restructuring may force a rebase of repo patch 0001 |
| AOTriton 0.14b | Replaces `VarlenType` with `VarlenBits` ("API BREAKING, BUT ABI STABLE") ([0.14b](https://github.com/ROCm/aotriton/releases/tag/0.14b)). Every PyTorch release branch still uses `VarlenType`; the port, pytorch#197747, is open on `main` only | Not selectable |
| TorchVision | 0.27.0 needs `torch==2.12.0` and 0.27.1 needs `torch==2.12.1` (PyPI); 0.28.0 needs `==2.13.0`; 0.29.0 needs `==2.14.0`. Python `>=3.10,!=3.14.1`. At v0.27.1, `setup.py` pins torch only when `PYTORCH_VERSION` or `PYTORCH_VERSION_GE/LT` is set | 0.27.1 from source |

### vLLM and the Python closure

| Component | Constraint (pinned source) | Result |
| --- | --- | --- |
| vLLM 0.30.0 | Python `>=3.10,<3.15`; gfx1151 in `HIP_SUPPORTED_ARCHS`; stable-ABI target 2.11; `transformers>=5.10.4`, `huggingface_hub>=1.31.0`, `tokenizers>=0.21.1`, `safetensors>=0.6.2`, `compressed-tensors==0.17.0`, `mistral_common[image]>=1.11.6`, `pydantic>=2.12.0`, `aiohttp>=3.13.3`, `openai>=2.25.0`, `prometheus-fastapi-instrumentator>=8.0.0` | Source build with `--no-build-isolation` |
| vLLM 0.30.0 ROCm CI lock ([test/rocm.txt](https://github.com/vllm-project/vllm/blob/ced6857afa0ea7b2e3f0846a62e1394e90f15607/requirements/test/rocm.txt); torch, TorchVision and Triton come from the base image) | Transformers 5.16.1, tokenizers 0.23.1, hub 1.31.0, mistral-common 1.11.6, compressed-tensors 0.17.0, safetensors 0.8.0, NumPy 2.2.6, pillow 12.1.1, pydantic 2.12.5 | C matches Transformers, compressed-tensors and safetensors exactly. The newer patch or minor versions elsewhere are metadata-admitted and covered by the host gates |
| Transformers 5.16.1 | `tokenizers>=0.23.1,<0.24.0`, `safetensors>=0.8.0`, `huggingface-hub>=1.5.0,<2.0`, `regex>=2025.10.22`, `typer` ([PyPI](https://pypi.org/project/transformers/5.16.1/)) | tokenizers 0.23.2, safetensors 0.8.0 |
| compressed-tensors 0.17.0 | `torch>=2.10.0`, `transformers>=4.45.0`, `pydantic>=2.0`, `loguru` | Admits the line |
| mistral-common 1.11.7 | Python `<3.15`; requires `pydantic-extra-types[pycountry]` since 1.11.7 | Admits the line. Add `python-pycountry` to the package depends |
| pydantic 2.13.5 | exactly `pydantic-core==2.46.5`; on a mismatch, `import pydantic` raises `SystemError` | pydantic-core 2.46.5 |

## Not selected from the frozen universe

| Observed version | Reason |
| --- | --- |
| Arch `python-pytorch-opt-rocm` 2.14.0-1 (upstream v2.14.0), and ROCm `release/2.14` `151661a6` | No vLLM release in the universe targets 2.14. TheRock 7.14.1 does not build it. The ROCm branch is unobserved. It needs a scikit-build-core rewrite. Keep it as the next PyTorch lane |
| ROCm `release/2.13` `9647b024` (version inside the universe; head not observed) | Rejected only under the X7 observation rule: the sweep did not observe the head. AMD's index does publish `torch-2.13.0+rocm7.14.0` (2026-09-03) |
| TorchVision 0.29.0 | Requires `torch==2.14.0` |
| AOTriton 0.14b | API break (`VarlenType` removed); no PyTorch branch is ported |
| AOTriton 0.13.50tp (in-tree pin at `13da0862`) | Pre-release tech preview that only adds gfx1250 tuning; 0.13b is the stable equivalent |
| compressed-tensors 0.19.0 | vLLM 0.28–0.30 pin `==0.17.0`. 0.19.0 also requires Transformers ≥ 5.16 at runtime and drops the GPTQ act-order paths |
| Transformers 5.17.0 | vLLM 0.30.0 `pixtral.py` imports removed symbols; the fix landed after the tag. vLLM 0.30 CI tested 5.16.1 |
| mistral-common 1.12.0 (uploaded 15:17Z on sweep day) | Not deprecations-only. Between v1.11.7 and v1.12.0 there are 29 commits, including new exceptions for malformed tool calls and continuation ([#310](https://github.com/mistralai/mistral-common/pull/310), [#325](https://github.com/mistralai/mistral-common/pull/325)), a validation mode ([#295](https://github.com/mistralai/mistral-common/pull/295)) and image-loading changes ([#308](https://github.com/mistralai/mistral-common/pull/308), [#316](https://github.com/mistralai/mistral-common/pull/316)) ([compare](https://github.com/mistralai/mistral-common/compare/v1.11.7...v1.12.0)). vLLM CI tested 1.11.6. 1.11.7 is the conservative choice |
| pydantic-core 2.49.0 (PyPI baseline) | Pairs only with pre-release pydantic 2.14.0b2. Arch pydantic 2.13.5 requires `==2.46.5` |
| AITER 0.1.22.post1 | Experimental on gfx1151 and outside the required path. The vLLM 0.30 AITER gate is CDNA3+ or gfx12 only. Removed in C's W5 transaction by default |
| llmcompressor 0.14.0, AutoRound 0.15.1 | Excluded from C's scope. Removed in C's W5 transaction by default |
| TheRock 10.0 (published 2026-08-26; masked from the sweep, see [Open risks](#open-risks)) | Newer than the observed 7.14.1, so the freeze excludes it. The approved end state names TheRock 7.14.x. No gfx1151 10.0 dist tarball exists in either AMD tarball index: `tarball-multi-arch/` stops at 7.14.1, and `tarball/` stops at 7.13.0 |

### Families outside C's closure

These sweep families are not in C's regenerated closure. They are
Arch-replacement optimization packages or belong to other lanes, and none of
the selected vLLM, Transformers or PyTorch packages requires them. Each stays
at the sweep's value and is dispositioned on its own:

- orjson 3.12.0, zstandard 0.25.0, cryptography 50.0.1, duckdb 1.5.5 and
  asyncpg 0.31.0: no C-line package depends on them.
- AOCL-LibM and AOCL-Utils 5.3.2: their only repo consumer is
  stable-diffusion.cpp.

These lanes are members of C without being on its required serving path:

- CTranslate2 4.8.2, through its security exception
  ([#120](https://github.com/nisavid/arch-strix-halo-pkgs/issues/120)).
- stable-diffusion.cpp, rebuilt because it links `rocm-llvm`
  ([#121](https://github.com/nisavid/arch-strix-halo-pkgs/issues/121)).

Lemonade and llama.cpp are exempt from the freeze or frozen in their own lane
([#137](https://github.com/nisavid/arch-strix-halo-pkgs/issues/137),
[#113](https://github.com/nisavid/arch-strix-halo-pkgs/issues/113)).

## W5 transaction removals

C's W5 activation transaction removes these packages by default. The owner can
override:

- `python-llmcompressor-gfx1151`
- `python-auto-round-gfx1151`
- `python-amd-aiter-gfx1151`

Their pacman depends are unversioned, so leaving them installed would break
them only at import time. The repo flash-attention package depends on the repo
AITER package, so removing AITER also forces a decision on that package.

## W1 plan (#108)

1. **CPython.** Build `python-gfx1151` 3.14.7: bump the version, checksum and
   the `Python-3.14.x` literals. Deciding on the Arch POSIX-2024 backport is
   an open question.
2. **Stage TheRock 7.14.1.** Commit the staging procedure so that F is built
   from repo recipes: tarball URL, sha256 and extraction.
3. **kpack gate, before rendering.**
   - Run `readelf -SW` on the main libraries to check for `.rocm_kpack_ref`,
     and inventory `.kpack/`.
   - If the payload is split, drop the `opt/rocm/.kpack/**` ignore, assign
     the archives to owning packages, and add an installed smoke that runs a
     kernel from a kpack-backed library.
4. **Build MIGraphX 2.16.1 (`2487b688`)** against the staged 7.14.1 root,
   using its compilers with no host `/opt/rocm` fallback, CPython 3.14.7, and
   protobuf 36.1 / abseil 20260817 in an isolated prefix. Keep MLIR OFF with
   the corrected stub patch. Validate the ONNX and TF parser `DT_NEEDED`
   entries and the Python import.
5. **Port from `nisavid/migraphx-protobuf-35-1-rebuild@0ae0d94`.**
   - Port:
     - `--migraphx-ref` fetch-by-SHA, pinned to `2487b688` (the branch pins
       `b69836e6`, a develop commit);
     - `pybind11_DIR` from `python -m pybind11 --cmakedir`;
     - the isolated protobuf prefix plus `LD_LIBRARY_PATH`;
     - both parser SONAME checks, generalized to "any SONAME ≠ build target",
       with SONAMEs derived at build time instead of hardcoded 35.x;
     - the `libprotobuf.so=<ver>-64` depends rendered from the build;
     - the tests.
   - Do not port the branch's July ledger or backlog docs. Record only the
     durable fact that 7.13.0-3 was deployed.
   - Keep the branch until the port merges.
6. **Render and fix policy.**
   - Set `pkgver = 7.14.1`, `pkgrel = 1`.
   - Expect loud generator failures for new artifacts (rocalution,
     hiptensor, hipfile, rocjitsu, sysdeps-util-linux, profiler examples)
     and removed ones (IREE, fusilli). Fix them in policy: add
     `rocalution-gfx1151` and `hipfile-gfx1151`, decide rocjitsu, render
     `hiptensor-gfx1151` if payload appears, and remove the dead IREE
     aliases.
   - Re-verify the rocm-smi post-copy fix.
7. **Build the split family and validate F in an isolated root.** Runtime,
   device enumeration, BLAS, kpack-backed kernel, MIGraphX import and parser
   smokes.
8. **Update freshness records.** In `policies/package-freshness.toml`, set
   therock `recorded = "7.14.1"` and ai-notes `dbfb70ef`. The ledger's
   `therock-7.14.1-stable` record already notes the TheRock 10.0 masking.

The PyTorch lane (#109) consumes this F. Its first build step is
`python-triton-gfx1151` at `669b31ac`, which re-derives the carry and the LLVM
`5f07f818` input. Then AOTriton 0.13b, then PyTorch `13da0862`: drop 0009,
rebase 0005, and optionally adopt Arch's `aotriton_disable_install.patch`.

## Open risks

1. **The sweep masked TheRock 10.0 (checker defect).**
   - [`latest_github_release`](../../../tools/check_package_updates.py)
     returns the first stable release in GitHub API order, not the PEP 440
     maximum. `therock-7.14.1` (published 08-31) is listed before
     `therock-10.0` (published 08-26, tag commit `16adc4d8`).
   - Among C-line release families, only TheRock is affected: vLLM,
     TorchVision and AOTriton report their PEP 440 maximum.
   - 7.14.1 stays, for two reasons. The approved end state names TheRock
     7.14.x. AMD publishes no gfx1151 10.0 dist tarball.
   - vLLM's `Dockerfile.rock_base` shows a first-party vLLM 0.30 pairing of
     torch 2.12 with TheRock 10.0, so 10.0 would not reopen every pairing.
     It stays excluded by the freeze.
   - The checker fix is routed to
     [#147](https://github.com/nisavid/arch-strix-halo-pkgs/issues/147).
2. **Live host hazard (pydantic).**
   - The host has `python-pydantic` 2.13.4 with the repo's
     `python-pydantic-core-gfx1151` 2.46.4.
   - Arch `python-pydantic` 2.13.5 depends on an unversioned
     `python-pydantic-core`. A routine `pacman -Syu` would therefore install
     a mismatched pair, and `import pydantic` would raise `SystemError`. That
     breaks vLLM, FastAPI, OpenAI, mistral-common and huggingface-hub
     consumers, including Open WebUI if it uses the system Python.
   - Fix status (2026-09-22): the package source moved to 2.46.5 and the
     package was built. It is not published or installed. The install rides
     the Lemonade install window
     ([#139](https://github.com/nisavid/arch-strix-halo-pkgs/issues/139)).
     Until then, hold `python-pydantic` at 2.13.4 through any host sync.
3. **The host is effectively held at protobuf 35.1.** Installed
   `migraphx-gfx1151` 7.13.0-3 depends on `libprotobuf.so=35.1.0-64`. The C
   activation transaction must carry protobuf 36.1, abseil 20260817 and the
   7.14.1 family together.
4. **The kpack device-code split is unverified.** This is a plausible
   high-impact risk: render and build would pass while kernels are missing at
   runtime.
5. **prometheus-fastapi-instrumentator stays at 7.0.0.** See
   [the divergence](#prometheus-fastapi-instrumentator-divergence) and its W6
   `/metrics` gate.
6. **vLLM 0.30 packaging is not a version bump.**
   - The 0016 carry needs a full re-port: 7 of its 29 target files are gone.
   - Model Runner V2 is the default. `VLLM_USE_V2_MODEL_RUNNER=0` restores
     MRV1 until v0.32.
   - The Rust extensions are optional, but `setuptools-rust` is required at
     build time.
   - `HIP_VISIBLE_DEVICES` replaces the `CUDA_VISIBLE_DEVICES` fallback.
   - The two server smoke tools use the deprecated `api_server` entry point.
7. **Triton package source-lane switch.**
   - The current package is ROCm `main_perf` `0ec280cf` with carry for a
     much older line.
   - 3.8.0 pins upstream LLVM `5f07f818`. By default it downloads a prebuilt
     LLVM (sha256 values in `llvm-info.json`). The recipe must pin and verify
     that input or build it.
   - Gemma 4 on `TRITON_ATTN` under Triton 3.8 is a live gate, because AITER
     is off the required path.
8. **ROCm 7.14 known issue #7898 applies to PyTorch below 2.14 on Ryzen AI
   Max.** Set `TORCH_BLAS_PREFER_HIPBLASLT=1`.
   - `13da0862` carries ROCm/pytorch#3316, which adds gfx1151 to the
     hipBLASLt preferred architectures on ROCm ≥ 7.13.
   - Confirm the effective BLAS backend in the installed smoke, and set the
     variable in scenarios or the service unit if needed.
9. **NumPy 2.5.3 postdates the PyTorch 2.12.0 release.** The vLLM CI uses
   2.2.6. NumPy 2.5 mostly expires Python-level deprecations, so the risk is
   low. Gate it with the torch, TorchVision and vLLM NumPy interop smokes;
   the fallback is the current 2.4.6.
10. **No first-party validation covers this exact combination.** AMD's ROCm
    7.14.1 table validates vLLM 0.23.0 on Python 3.14 with PyTorch 2.11.0.
    vLLM 0.30's ROCm CI runs Python 3.12 with Triton 3.7.x. The build and
    live gates are the only validation for C.

## Source disposition

All sources were retrieved on 2026-09-22. No local result was promoted.

| Source | Type and exact ref | Extracted value | Status |
| --- | --- | --- | --- |
| [ROCm PyTorch `13da0862`](https://github.com/ROCm/pytorch/commit/13da08625e0d25586351146b4c444f5263997ef8) | First-party source, `release/2.12` head | 2.12.0; Triton `669b31ac`; AOTriton API range; `related_commits` vision `release/0.27` | `requires-host-validation` |
| [ROCm Triton `669b31ac`](https://github.com/ROCm/triton/commit/669b31acc1dd1b3fd93286afd5db67f65d9f7557) | First-party source, `release/internal/3.8.x` head | 3.8.0; LLVM `5f07f818`; 24 commits after `4cff872c` | `requires-host-validation` |
| [AOTriton 0.13b](https://github.com/ROCm/aotriton/releases/tag/0.13b) / [0.14b](https://github.com/ROCm/aotriton/releases/tag/0.14b) | First-party releases | 0.13b `6e00ef3e` with vendored Triton `db82b800`; 0.14b API break | `planned` / `rejected` |
| [TheRock 7.14.1](https://github.com/ROCm/TheRock/releases/tag/therock-7.14.1) | First-party release, `f51dc6c9` | PyTorch matrix 2.10–2.12; Triton from the torch pin; kpack default | `requires-host-validation` |
| [ROCm 7.14.1](https://rocm.docs.amd.com/en/docs-7.14.1/about/release-notes.html) and [10.0](https://rocm.docs.amd.com/en/docs-10.0.0/about/release-notes.html) release notes | First-party documentation | Framework tables; #7896 and #7898 known issues | `advisory-only` |
| [AMD multi-arch wheel index](https://repo.amd.com/rocm/whl-multi-arch/) | First-party distribution; wheel METADATA read by HTTP range request | `torch-2.12.0+rocm7.14.{0,1}`, `torch-2.13.0+rocm7.14.0`, `torchvision-0.27.0+rocm7.14.1`, `torchvision-0.28.0+rocm7.14.0` and their Triton pins | `advisory-only` |
| [AMD multi-arch tarball index](https://repo.amd.com/rocm/tarball-multi-arch/) | First-party distribution | gfx1151 7.14.0 and 7.14.1 tarballs; no 10.0 | `planned` |
| [AMDMIGraphX `2487b688`](https://github.com/ROCm/AMDMIGraphX/commit/2487b688c453b9007ac69ff1d79ad6cf9b509901) | First-party source, `release/rocm-rel-7.14` head | 2.16.1 for ROCm 7.14.1 | `requires-host-validation` |
| [vLLM `v0.30.0`](https://github.com/vllm-project/vllm/releases/tag/v0.30.0) (`ced6857`) | First-party release | CMake, pyproject, requirements, ROCm Dockerfiles, CI locks | `requires-host-validation` |
| [vllm#50605](https://github.com/vllm-project/vllm/pull/50605) | First-party pull request, open | Triton 3.8 kernel port for non-required model families | `advisory-only` |
| [mistral-common v1.11.7...v1.12.0](https://github.com/mistralai/mistral-common/compare/v1.11.7...v1.12.0) | First-party compare | New validation raises, validation mode, image-loading changes | `rejected` |
| PyPI metadata: [torchvision](https://pypi.org/project/torchvision/0.27.1/), [transformers](https://pypi.org/project/transformers/5.16.1/), [tokenizers](https://pypi.org/project/tokenizers/0.23.2/), [safetensors](https://pypi.org/project/safetensors/0.8.0/), [compressed-tensors](https://pypi.org/project/compressed-tensors/0.17.0/), [mistral-common](https://pypi.org/project/mistral-common/1.11.7/), [numpy](https://pypi.org/project/numpy/2.5.3/), [pydantic](https://pypi.org/project/pydantic/2.13.5/), [accelerate](https://pypi.org/project/accelerate/1.15.0/), [aiohttp](https://pypi.org/project/aiohttp/3.14.3/), [huggingface-hub](https://pypi.org/project/huggingface-hub/1.32.0/), [prometheus-fastapi-instrumentator](https://pypi.org/project/prometheus-fastapi-instrumentator/8.0.0/) | Maintainer-published metadata at the cited versions | Exact pins, floors and Python ranges | `advisory-only` until packaged and tested |
| [Arch `python` 3.14.7-1](https://gitlab.archlinux.org/archlinux/packaging/packages/python/-/commit/3254b07) | Distribution packaging | POSIX-2024 backport | `planned` |

Future sessions should not re-check the moving branches for C: X7 freezes
this line. The next 24-hour sweep records any later drift as post-closeout
maintenance ([#147](https://github.com/nisavid/arch-strix-halo-pkgs/issues/147)),
except for security fixes or build breakage.
