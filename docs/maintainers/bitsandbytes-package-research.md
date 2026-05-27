# bitsandbytes Package Research

Status as of 2026-05-27.

This note prepares a future `python-bitsandbytes-gfx1151` package lane. It is a
source and provenance research artifact only. It does not add package policy,
package files, source updates, package builds, deploy/install work, installed
smokes, or live inference validation.

## Source Pin

Use upstream `bitsandbytes-foundation/bitsandbytes` tag `0.49.2` as the
candidate package source:

- tag: `0.49.2`
- commit: `f0e6ca31b32c4744a9cee4e31610b25796cbf778`
- license: MIT, from the upstream `LICENSE` file
- source URL:
  <https://github.com/bitsandbytes-foundation/bitsandbytes/releases/tag/0.49.2>

The upstream `main` branch has moved past the release tag. Treat `main`, the
continuous preview wheels, and older ROCm fork guidance as advisory unless a
future lane deliberately chooses a newer source pin.

Do not use PyPI or PyTorch-index binary wheels as package sources. PyPI release
metadata may confirm version existence, but the local package source must be a
pinned upstream source archive or git commit that the PKGBUILD verifies.

## ROCm Build Shape

The tagged source already carries a HIP backend in `CMakeLists.txt`.
Packaging should build it explicitly for Strix Halo:

- set `COMPUTE_BACKEND=hip`
- set `BNB_ROCM_ARCH=gfx1151` even though the tagged default HIP target list
  includes `gfx1151`
- build from the release source, not from the preview wheel artifacts
- keep `ROCM_PATH` on the system ROCm installation unless the package lane has
  a reviewed reason to override it

The HIP build appends `_rocm<hip-version>` to the native library name using
`hipconfig --version`. The installed diagnostic path looks up the library name
from PyTorch's HIP version. A future package lane must verify that the
`hipconfig` value used during the package build matches the installed
`torch.version.hip` value from `python-pytorch-opt-rocm-gfx1151`; a mismatch can
produce a built library that diagnostics and consumers do not load.

The HIP backend links ROCm libraries through CMake packages for `hipblas`,
`hiprand`, and `hipsparse`, and links `hipblaslt` when the detected HIP version
is at least 6.1. The package dependency set should come from the installed
ROCm/TheRock split packages that provide those CMake package files and runtime
libraries.

The upstream release documentation marks AMD ROCm support as preview. It lists
Python `>=3.10`, PyTorch `>=2.3,<3`, NumPy, and Packaging as runtime
requirements; the tagged project metadata includes Python 3.14 classifiers.
The ROCm source-build instructions require CMake `>=3.31.6`, while the tagged
`CMakeLists.txt` declares `cmake_minimum_required(VERSION 3.22.1)`. Use the
documented ROCm requirement when choosing package build dependencies unless a
future source build proves the lower project minimum is sufficient.

## Test And Smoke Gates

The future package lane should derive validation before implementation, then
keep source updated, package built, deployed/installed, installed-smoked, and
live-scenario validated states separate.

Required source/package gates:

- source verification for the selected tag archive or git commit
- source preparation with `COMPUTE_BACKEND=hip` and `BNB_ROCM_ARCH=gfx1151`
- native library inspection proving the installed package contains the ROCm
  library name expected by the installed PyTorch HIP version
- package-local tests for renderer or packaging metadata if the lane adds
  recipe-managed package policy

Required installed smokes:

- `python -m bitsandbytes` against the installed package
- a direct `bitsandbytes.nn.Linear4bit` smoke on the ROCm device for both `nf4`
  and `fp4`, with finite output and ROCm-valid block sizes
- a direct `bitsandbytes.nn.Linear8bitLt` smoke on the ROCm device, with finite
  output and comparison against a small PyTorch linear baseline
- a pinned Transformers model smoke using `BitsAndBytesConfig(load_in_4bit=True)`
- a pinned Transformers model smoke using `BitsAndBytesConfig(load_in_8bit=True)`

The upstream test suite has useful direct surfaces in `tests/test_linear4bit.py`,
`tests/test_linear8bitlt.py`, `tests/test_ops.py`, and
`tests/test_generation.py`. Use those files as source-test references, but do
not treat an unbounded upstream test run as the package acceptance gate. The
package gate should be a bounded installed smoke set that proves the local
system package is loadable and useful with the installed ROCm PyTorch stack.

## Consumer Gates

Transformers is the first consumer gate. The smoke model must have an explicit
repository, revision, and license/provenance record before the live run. Do not
use `trust_remote_code=True` unless the model code has a source review and the
scenario records why that risk is accepted.

vLLM is a later exploratory consumer gate. Current vLLM documentation has a
BitsAndBytes loader path, but its visible hardware support matrix marks
BitsAndBytes unsupported on AMD GPU, and AMD ROCm vLLM quantization guidance
does not list BitsAndBytes among the optimized or supported ROCm quantization
methods. Treat a vLLM BitsAndBytes run as a required proof point before saying
the package benefits `python-vllm-rocm-gfx1151`.

A vLLM smoke must:

- use a pinned BitsAndBytes-quantized model revision with license/provenance
  recorded in the scenario definition
- assert that vLLM selects the BitsAndBytes quantization/load path
- run with bounded context and memory settings suitable for the reference host
- record source, installed-package, installed-smoke, and live-scenario states
  separately

## Implementation Blockers

Do not implement this package in the current docs-only lane.

Open a separate implementation lane only after the active stable runtime-base
work is closed or the coordinator explicitly approves a bypass. The current
blocking sequence is:

1. close the remaining ROCm PyTorch runtime-base live-validation follow-up or
   explicitly accept its bypass
2. close or explicitly bypass the ROCm PyTorch release/2.12 `980ce60`
   follow-up if it remains part of the runtime-base decision
3. close or explicitly bypass the Transformers 5.9.0 follow-up because the
   primary consumer gate depends on installed Transformers behavior
4. pin model fixtures and provenance for the Transformers and vLLM smokes
5. then implement `python-bitsandbytes-gfx1151` package policy and package
   files in a package lane

## Review Risks

- Preview ROCm support means source-build success is not enough; the local
  installed smokes decide package usefulness.
- Binary wheels can mask source-build failures and can also pull dependency
  variants that do not match the local ROCm PyTorch stack.
- `python -m bitsandbytes` and failed model loaders can print environment
  paths. Do not commit raw logs until private paths and cache roots are
  removed.
- Model repositories are untrusted inputs. Record license and provenance before
  using a model as an acceptance fixture.
