# Current State

Status as of 2026-04-28.

## Rebuild Revalidation Boundary

Runtime and inference findings recorded before the 2026-04-20 self-hosted
rebuild confidence boundary were treated as historical evidence until they
were reproduced against the rebuilt stack. The closed quarantine record for
local-origin patch rationale, expected-failure tests, and backlog findings
lives in [the rebuild revalidation ledger](rebuild-revalidation.md).

The full native package rebuild and install completed on 2026-04-20 through
`tools/amerge` plan `20260420T045008-685264b1`, with 75 completed steps and no
remaining failed steps. Build/deploy closeout for the native stack is complete;
post-rebuild revalidation closeout is recorded in the revalidation ledger.
Follow-up official vLLM recipe coverage now lives in
`docs/maintainers/vllm-recipe-coverage.md`.

## ROCm inference reference boundary

`docs/maintainers/rocm-inference-reference.md` records ROCm examples,
MIGraphX, Torch-MIGraphX, FlashAttention, profiling, quantization, and vLLM
optimization references retrieved on 2026-04-22.

This does not change validated host behavior. Treat new package and scenario
ideas from that reference as planned or advisory until source audit, package
work, and local gfx1151 validation update this file or the recipe coverage
ledger.

The `migraphx-gfx1151` split now exposes a real MIGraphX payload on the
reference host. On 2026-04-22, `pacman -Q migraphx-gfx1151` reported
`7.13.0pre-5`, and `import migraphx` loaded
`/opt/rocm/lib/migraphx.cpython-314-x86_64-linux-gnu.so` with MIGraphX
package version `2.16.0.dev+479da6b`. The staged TheRock path that produced
that package builds AMDMIGraphX for `gfx1151`, patches current upstream's
no-rocMLIR build gaps, and renders real MIGraphX binaries, shared libraries,
private headers, Python extension payloads, and `migraphx.pth`.

The `python-torch-migraphx-gfx1151` package policy now exists for the audited
ROCm/torch_migraphx `master` commit
`6b2cd2237e83b675ae671650d08343dfbb0be5f3`, which reports package version
`1.2` while PyPI and the only upstream tag remain at `1.1`. The local package
binds builds to the ROCm compiler lane, carries a PT2E import patch for the
PyTorch 2.11 and TorchAO layout, keeps Dynamo registration lazy on base import,
and preloads PyTorch AOTAutograd before MIGraphX native modules so
named-backend registration avoids the local import-order segfault. `tools/amerge build
python-torchao-rocm-gfx1151 python-torch-migraphx-gfx1151` produced
`python-torchao-rocm-gfx1151 0.17.0-2` and
`python-torch-migraphx-gfx1151 1.2-2` package artifacts on 2026-04-22. The
reference host then installed `python-torchao-rocm-gfx1151 0.17.0-2` and
`python-torch-migraphx-gfx1151 1.2-2`; installed-system imports for TorchAO
PT2E, Torch-MIGraphX, and MIGraphX resolve from package-owned paths, and a
host-device FX smoke lowered a tiny `x + 1` module to a MIGraphX-backed
`SplitModule` on the Radeon 8060S with matching PyTorch output. A follow-up
`python-torch-migraphx-gfx1151 1.2-3` adds the AOTAutograd preload patch; the
installed package imports `torch_migraphx.dynamo`, imports `sqlite3` after
Torch-MIGraphX, and passes the same tiny module through
`torch.compile(..., backend="migraphx")` on the reference host.

`python-torch-migraphx-gfx1151 1.2-4` extends the PT2E compatibility patch to
Torch-MIGraphX's `MGXQuantizer`, quantizer utility imports, and TorchAO
observer wrappers. After deploy on 2026-04-22, `pacman -Q
python-torch-migraphx-gfx1151` reports `1.2-4`. The installed scenario run
`docs/worklog/inference-runs/20260422T145151` passed
`torch-migraphx.pt2e.quantizer-import`, `torch-migraphx.resnet-tiny.dynamo`,
and `torch-migraphx.resnet-tiny.pt2e` on the Radeon 8060S with matching
PyTorch output. The Dynamo ResNet-style smoke reported baseline
`0.3008 ms`, compiled `0.1725 ms`, speedup `1.7440`, max absolute difference
`0.00000001`, and peak memory `33739776` bytes. The PT2E ResNet-style smoke
reported baseline `0.4356 ms`, compiled `0.2323 ms`, speedup `1.8750`, max
absolute difference `0.00000001`, and peak memory `33802752` bytes.

Keep Composable Kernel and rocMLIR integration disabled unless explicitly
requested, because the current staged root is intentionally self-consistent
with the installed split packages before those optional integration gates are
promoted.

The preflight freshness sweep for the FlashAttention package experiment was
triaged on 2026-04-22. No existing package source was repinned during that
triage: AITER main through `5162472c87d0cb18b1a9fc0ee85949881073593c` added
gfx942/gfx950 tuning, logging, MHA test coverage changes, and GLM-shaped A8W8
configs, with no change to the gfx1151 OPUS FP8, RDNA header, JIT, or AITER
MoE patch touchpoints; ROCm PyTorch release/2.11 through
`50bfde7c08dc92b69b71d2b76d3b2d3709cf28f6` added ROCm Inductor GEMM,
pointwise, and reduction config coverage without overlapping the local Python
3.14 wheel flow, HIPGraph stub, NumPy target define, MAGMA version encoding,
gfx1151 CK enablement, or BLAS/provider carry; llama.cpp `b8884` at
`750579ff14198fe964ab7fc5565b1d77600deab4` was a sampler-parameter
front-end refactor in common/CLI/server code, not a HIP/Vulkan backend change;
and Transformers `5.6.0` was reviewed as a broader Gemma/model/rotary-kernel
release that belongs to the Transformers/Gemma closure lane, not the direct
FlashAttention build/import gate. The new
`python-flash-attn-rocm-gfx1151` freshness family records ROCm
FlashAttention `main_perf` at `3f94643fb41bcedded28c85185a8e11d42ef1592`.
The reviewed values are recorded in `policies/package-freshness.toml`; the
later llama.cpp b8892 sweep below supersedes this as the current freshness
boundary.

The next freshness sweep found llama.cpp upstream `b8892`. The
`llama.cpp-hip-gfx1151` and `llama.cpp-vulkan-gfx1151` package definitions now
track `b8892` at commit `0d0764dfd257c0ae862525c05778207f87b99b1c`, and
`policies/package-freshness.toml` records `b8892` as the reviewed release. The
`b8884..b8892` review found HunyuanVL model-loading and mtmd updates, server
transcription and tool-call handling changes, WebGPU/SYCL code changes, and
speculative example checkpointing. No HIP- or Vulkan-specific build-system
change was found, but the server/tool source delta is relevant to the packaged
runtime. The 2026-04-22 20:41 EDT refreshed freshness sweep then reported all
24 families current. Treat package freshness as satisfied until that completed
sweep is older than 24 hours or invalidated by package policy, package
directory, checker-logic, or relevant source-metadata changes.

The 2026-04-23 21:51 EDT refreshed freshness sweep found actionable updates in
five lanes and updated `policies/package-freshness.toml` with the reviewed
heads. llama.cpp `b8911` at commit
`5d2b52d80d9f375a6e81d07e212d047d8ee4f76e` was adopted for both HIP and
Vulkan packages because the `b8892..b8911` range flips HIP graphs on by
default, includes shared server/API fixes, fixes CVE-2026-21869 negative
`n_discard` handling, and updates ModelOpt mixed-precision GGUF conversion.
The same sweep reviewed but did not repin AITER main through
`8432ff3b6e356bc0f8c664a686334e3be7e736ec`, ROCm PyTorch `release/2.11`
through `0320cc5b2fbba866c7ac1aa5deb8c14dd9a37b95`, Transformers `5.6.2`,
and Blackcat Informatics `upstream/ai-notes` main through
`c4dbe5046f45550c2e0bfd8fc49101a992c08076`. Those reviewed ranges either do
not overlap current local patch/runtime touchpoints or remain gated behind a
separate package/scenario validation lane. Treat package freshness as
satisfied until this sweep is older than 24 hours or invalidated by package
policy, package directory, checker-logic, or relevant source-metadata changes.
`tools/amerge build llama.cpp-hip-gfx1151 llama.cpp-vulkan-gfx1151
lemonade-server` plan `a9437361` completed and produced
`llama.cpp-hip-gfx1151-b8911-1-x86_64.pkg.tar.zst`,
`llama.cpp-vulkan-gfx1151-b8911-1-x86_64.pkg.tar.zst`, and
`lemonade-server-10.2.0-5-x86_64.pkg.tar.zst`. Host deploy then completed:
`tools/amerge deploy llama.cpp-hip-gfx1151 llama.cpp-vulkan-gfx1151
lemonade-server` plan `db292c1d` installed those artifacts. `pacman -Q`
reports `llama.cpp-hip-gfx1151 b8911-1`,
`llama.cpp-vulkan-gfx1151 b8911-1`, and `lemonade-server 10.2.0-5`.

On 2026-04-24, the repo adopted the reviewed Blackcat Informatics
`upstream/ai-notes` recipe input at
`c4dbe5046f45550c2e0bfd8fc49101a992c08076` and onboarded
`python-duckdb-gfx1151` from the new native-wheel recipe note. The package is
rendered from `policies/recipe-packages.toml` with Arch `extra/python-duckdb`
as the authoritative reference and CachyOS `python-duckdb` as advisory, and
`policies/package-freshness.toml` tracks DuckDB against PyPI `1.5.2` and Arch
`python-duckdb 1.5.2-1`. `makepkg --verifysource` and
`makepkg --printsrcinfo` pass for the new package. The first
`tools/amerge run python-duckdb-gfx1151` attempt stopped before compilation
because the host was missing the transient makedepend
`python-scikit-build-core`; after that dependency was installed, the next
attempt reached DuckDB's no-isolation build dependency check and exposed that
Arch's `cmake` and `pybind11` packages do not satisfy DuckDB's PyPI metadata
names `cmake` and `pybind11[global]`. The package now sets
`skip_dependency_check = true`, keeps the actual Arch makedepends explicit,
and `tools/amerge build python-duckdb-gfx1151` plan `b9882393` produced
`python-duckdb-gfx1151-1.5.2-1-x86_64.pkg.tar.zst`. A staged package-tree
smoke imported `duckdb 1.5.2` and returned `[(42,)]` for `select 21 * 2`.
The first deploy attempt could not validate sudo noninteractively, but after
host install `pacman -Q` reports `python-duckdb-gfx1151 1.5.2-1` with
`python-gfx1151 3.14.4-1`. The installed-system smoke imported `duckdb 1.5.2`
from `/usr/lib/python3.14/site-packages/duckdb/__init__.py` and returned
`[(42,)]` for `select 21 * 2`.

The same policy-invalidated freshness recheck reviewed llama.cpp `b8913` at
commit `e5f070a1dca19baf3ae983273846b9a8c7c4231f`. The `b8911..b8913` range
only touches WebGPU RMS-fuse aliasing and a CLI cleanup for redundant local
sampling variables, so the local HIP/Vulkan packages remain pinned to the
already built and deployed `b8911` source while `policies/package-freshness.toml`
records `b8913` as the reviewed release head.

The same recheck also reviewed AITER main through
`ed2db5ef0f6444b735f018c0f4688058c1bfeb26`. The
`8432ff3b6e356bc0f8c664a686334e3be7e736ec..ed2db5ef0f6444b735f018c0f4688058c1bfeb26`
range contains two CI-only changes plus a Gluon paged-attention decode
sliding-window MTP fix. Keep that recorded as a reviewed candidate head for
future speculative/MTP validation, but the packaged AITER source remains pinned
to the current host-validated commit because this range does not address the
gfx1151 OPUS FP8 `mfma_adaptor` gap or replace the package's local JIT/RDNA
patch carry.

During main-branch closeout on 2026-04-24, the live freshness gate found
llama.cpp `b8914` and AITER main
`f1f5e0674d7381c565b4ea33c25d7d584cae85c7`. llama.cpp `b8913..b8914` is the
Hexagon-only `SOLVE_TRI` op addition, and AITER
`ed2db5ef0f6444b735f018c0f4688058c1bfeb26..f1f5e0674d7381c565b4ea33c25d7d584cae85c7`
only changes CI workflow files. `policies/package-freshness.toml` records both
as reviewed without repinning package sources.

The 2026-04-24 22:06 EDT upstream-refresh pass adopted the reviewed Blackcat
Informatics `upstream/ai-notes` recipe input at
`a188f9e5821b851870a81fd428508f19d26565ef`, which integrates gfx1151 build
hardening from the Dillflix fork. The rendered recipe package scaffolds now
record recipe revision `a188f9e` and the 37-step upstream pipeline. The
upstream manifest also removes its blanket vLLM Triton sampler bypass and adds
PyTorch/ROCm hardening notes; local package policy still keeps the repo-owned
vLLM sampler patch until the tracked gfx1151 large-vocabulary sampler failure
is revalidated.

The same refresh reviewed and recorded without repinning package sources:
cryptography PyPI `47.0.0` while Arch `python-cryptography` remains
`46.0.7-1`; llama.cpp `b8925` at
`0adede866ddb2e31992b3792eaea31d18ed89acf` plus AUR
`llama.cpp-hip b8925-1`; ROCm PyTorch `release/2.11` at
`3aaa914af1e6fb268b242bfb871e614fbdb6c1bc`; and AITER `main` at
`033d8b9dbc635d30aa63906245c045f24f8cf796` with release tag
`0.1.12.post2`. PyTorch's reviewed delta is a Windows MIOpen CTC-loss fix.
The AITER range adds Qwen3.5/GDN, large-KV batch-prefill, top-k-per-row, and
fused-MoE work that belongs behind a tracked Qwen/GDN or fused-MoE validation
lane before repinning. The llama.cpp range includes parser structured-output
fixes, server SWA-full and cache-idle-slots cleanup, Jinja warning fixes,
WebGPU FlashAttention work, Metal device logging, and Hexagon/Snapdragon
updates; keep it reviewed until a runtime rebuild lane is opened. A post-update
forced checker run reported no actionable package statuses and 22 current
families, but the AUR provider still failed with SSL EOF for
`python-sentencepiece`, `python-torchvision-rocm`, and `python-vllm`. Treat the
freshness gate as blocked on those provider retries rather than an untriaged
package update.

A 2026-04-24 23:15 EDT retry narrowed the blocker to AUR provider
availability, not package drift or checker parsing. The forced narrow checker
run for `sentencepiece`, `torchvision`, and `vllm` reported `torchvision` and
`vllm` current once, but still failed the `python-sentencepiece` AUR baseline
with `SSL: UNEXPECTED_EOF_WHILE_READING`. A follow-up `vllm`-only run then
timed out on the `python-vllm` AUR baseline. Direct `curl` requests to
`aur.archlinux.org` and AUR RPC endpoints reproduced the TLS EOF while Arch
package search, PyPI, and GitHub requests succeeded. GitHub currently lists
`v0.20.0` for vLLM as a prerelease, so the checker's stable-release result of
`0.19.1` remains expected. Treat the freshness gate as still blocked on an AUR
provider retry.

The 2026-04-25 06:24 EDT retry cleared the AUR provider blocker:
`sentencepiece`, `torchvision`, and `vllm` all reported current. A full forced
freshness sweep then found three actionable statuses, all reviewed and recorded
without adopting new package sources. Arch `python-cryptography` moved to
`47.0.0-1`, matching the already reviewed PyPI release; Arch's current
PKGBUILD uses `python-maturin`, `clang`, `lld`, `llvm`, `python-setuptools`,
and `python-wheel`, so keep the local package on `46.0.7` until a
package-specific build refresh validates that newer maturin lane. llama.cpp
`b8925..b8929` changes SYCL, WebGPU SSM_SCAN, docs, and `llama-quant`'s
default quantization type from `Q5_1` to `Q8_0`; no HIP/Vulkan package-build
touchpoint was found, so keep the installed packages pinned to the deployed
`b8911` source until a runtime rebuild lane opens. Blackcat Informatics
`upstream/ai-notes` main moved to
`9f7c85f264287ac744272ce540e87058c7a3296b`; the reviewed range adds Bitserv
Qwen3-VL W8A16 artifacts, a stable-diffusion.cpp Vulkan build lane, a
`file_copy` parent-directory fix, and llama.cpp Vulkan optimization notes.
Record that head as reviewed, but do not bump the submodule without an
explicit package/scenario adoption lane.

The 2026-04-25 TheRock coverage audit for `hipfort-gfx1151` and
`mivisionx-gfx1151` found no payload under the live `/opt/rocm`, current
generated file lists, or current local package artifacts. The repo package
graph therefore correctly treats both names as unknown outputs until a render
uses a staged root that contains them. Policy aliases and regression tests now
cover representative Arch-family payload shapes for hipFORT and MIVisionX, so
a future staged TheRock root with those files should render package functions
and file lists rather than fail classification.

The same 2026-04-25 TheRock baseline audit aligned
`rocm-debug-agent-gfx1151` with Arch/CachyOS `rocr-debug-agent`: the local
package now provides and replaces `rocr-debug-agent`, keeps the
`rocm-debug-agent` provide, and depends on the local `rocm-core`,
`hip-runtime-amd`, and `rocm-dbgapi` split packages. The audit also stopped
rendering fileless `hiptensor-gfx1151` and `rpp-gfx1151` compatibility
packages because current Arch/CachyOS `hiptensor` and `rpp` are real payload
packages and the current staged TheRock root contains no matching payloads.
The local HIP and ML meta packages therefore no longer depend on those names
until a staged root can support real package contents.

The generated-package deployment was verified on 2026-04-25: `pacman -Q`
reports `rocm-debug-agent-gfx1151`, `rocm-hip-libraries-gfx1151`, and
`rocm-ml-libraries-gfx1151` at `7.13.0pre-5`; the debug-agent package provides
and replaces `rocr-debug-agent`; the HIP and ML meta packages no longer depend
on `hiptensor-gfx1151` or `rpp-gfx1151`; and those former zero-payload
packages are absent from both the installed package database and
`repo/x86_64`.

The same baseline audit tightened core runtime dependency metadata in
`policies/therock-packages.toml`: `comgr`, `hsa-rocr`, `rocminfo`,
`rocm-device-libs`, `rocm-language-runtime`, `rocm-hip-runtime`,
`hip-runtime-amd`, `rocm-cmake`, `rocm-smi-lib`, `amdsmi`,
`rocm-opencl-runtime`, `rocm-opencl-sdk`, and `rocm-dbgapi` now carry
Arch/CachyOS-style dependency edges using local `-gfx1151` package names where
appropriate. The OpenCL runtime now provides `opencl-driver` but no longer
claims `rocm-ocl-icd` or `rocm-opencl-icd-loader`; it depends on the system
OpenCL ICD loader instead.

The audit then tightened rendered math, profiler, and ML dependency metadata:
BLAS, FFT, sparse, RAND, decode/JPEG, MIOpen, MIGraphX, RCCL, Composable
Kernel, rocProfiler, roctracer, and AQL profiling split packages now carry
Arch/CachyOS-style dependencies using local `-gfx1151` package names where
appropriate. `hipify-clang-gfx1151` keeps the Arch-style compiler/runtime
dependencies but intentionally omits Arch's `cuda` dependency so this AMD ROCm
family does not pull a CUDA stack for the HIP translation tool.

The same audit is now current through the rendered TheRock family. Remaining
non-matching package names are local support exceptions rather than unchecked
baseline gaps. `rocm-hip-gfx1151`, `hip-gfx1151`, and `hipcc-gfx1151` keep
local meta/package surfaces that compose the generated HIP SDK around TheRock's
payload. `rocprofiler-sdk-gfx1151`, `rocprofiler-sdk-roctx-gfx1151`,
`rocprofiler-sdk-rocpd-gfx1151`, `rocprofiler-compute-gfx1151`,
`rocshmem-gfx1151`, `rocm-host-math-gfx1151`, and `rocm-sysdeps-gfx1151` do
not currently have exact Arch package counterparts to mirror. `miopen-gfx1151`
stays split from `miopen-hip-gfx1151` because the local generated family keeps
TheRock payload ownership separate from the Arch `miopen-hip` naming surface.
The fileless meta packages remain intentional composition packages. Reopen this
audit when Arch adds matching package surfaces, CachyOS changes ROCm metadata
shape, or a future staged TheRock root changes the payload set.

The 2026-04-25 patch-carry cleanup moved `python-triton-gfx1151`'s stabilized
source edits out of inline `prepare()` sed/cherry-pick commands and into three
package-local patch files: Python 3.14 and pybind11 build-system compatibility,
`-Werror` removal for the local LLVM/header lane, and
`AttrsDescriptor.__repr__` for Inductor codegen. The Triton recipe policy now
lists those files as `source_patches`, and the renderer applies them directly
for the ROCm Triton template. The policy-invalidated freshness sweep after this
change reported all 25 package families current.

The same patch-carry cleanup moved `aocl-libm-gfx1151`'s SCons toolchain
source edits into `0001-scons-support-arch-amdclang-toolchain.patch`. The patch
removes the AOCC-only unaligned-vector flag, keeps macro-redefinition warnings
from failing the package build, and uses Clang/GNU-ld-compatible entry-point
linker flags for the hand-written assembly objects. The AOCL-LibM renderer now
applies package `source_patches` instead of recipe sed actions while preserving
the post-install RPATH fix in `package()`.

On 2026-04-26, the patch-carry cleanup moved three
`python-pytorch-opt-rocm-gfx1151` `prepare()` source edits into package-local
patches: the NumPy 2 target C-API define, removal of the HIP
`-fclang-abi-compat=17` flag for the local amdclang lane, and gfx1151
Composable Kernel GEMM enablement. The PyTorch renderer now applies those
files through package `source_patches` instead of emitting inline `sed`
commands, while the generated HIPGraph rewrite remains a build-time generated
source fix because that file is produced only after PyTorch's AMD build helper
runs.

The policy-invalidated 2026-04-26 freshness sweep found AITER main
`dcb0639d870783c2bc0c530e465f301032e756dc`, llama.cpp `b8935` at
`f454bd7eb8944629aabca163ea1c6e67e53fd77e`, and AUR `llama.cpp-hip
b8933-1`. The AITER range only optimizes the mHC prefill kernel for small M
and updates its op test, so it does not affect the current gfx1151 RDNA header
patches, JIT runtime patch, gfx1x MoE carries, or Qwen3.6 FP8 OPUS blocker.
The llama.cpp range adds OpenCL IQ4_NL support, CUDA MMQ overhead reduction,
Metal Tensor API optimization, a Hexagon HMX clock guard, chat
reasoning-marker spacing fixes, and speculative vocab compatibility checks; no
HIP or Vulkan package-build touchpoint was found. `policies/package-freshness.toml`
records those heads as reviewed without repinning package sources. A forced
post-triage checker run then reported all 25 package families current.

The 2026-04-28 freshness refresh found AITER main
`6a7df2004f5f896471cf9e6ab588b6aec0357dc7`, llama.cpp `b8953` at
`434b2a1ff6a73927f1aeef1455599fbe207f7d6f`, AUR `llama.cpp-hip b8953-1`,
ROCm PyTorch `release/2.11` at
`e16e349eb30bac8fd72b5c34ab220527fea5c58c`, Arch
`python-pytorch-opt-rocm 2.11.0-4`, vLLM `0.20.0`, and Blackcat Informatics
`upstream/ai-notes` main at `a1d7a6816dd2c456bad9fcc7d61c53a4bd8c5fbd`.
The reviewed AITER range adds Triton A16W4 MoE kernels, MHA backward stride
fixes, an mHC device fix, gfx950 A8W8 correctness updates, and CI workflow
changes, but does not resolve the gfx1151 OPUS FP8 `mfma_adaptor` blocker or
replace local RDNA/JIT patch carry. The llama.cpp range adds WebGPU Q1_0 and
matmul tuning, fast i-quant mat-vec kernels, CPU/AMX optimizations, q8_0
download preference, model conversion cleanup, Qwen/LLaMA duplicate-scale
removal, server router form-data forwarding, and Windows RPC/cache fixes; no
HIP or Vulkan package-build touchpoint was found. The PyTorch range is limited
to Windows DLL-export/native-header and MIOpen CTC-loss fixes, with no overlap
against the current gfx1151 wheel assembly, HIPGraph stub, NumPy target
define, CK enablement, or BLAS/provider carry.

The vLLM 0.20.0 release is relevant but too broad for a freshness-only bump:
it adds first-party Python 3.14 and torch 2.11 metadata support, DFlash
model/runtime pieces, broad quantization and MoE refactors, ROCm
memory-shutdown and NUMA detection fixes, GDN and Gemma 4 changes,
pooling/scoring route reshaping, and many entrypoint changes that overlap
local patch carry and tracked validation lanes. The newer Blackcat recipe
input adds Stable Diffusion, Qwen3-VL embedding, vLLM environment/package, and
new vLLM patch material. Treat both as dedicated package-update or recipe
lanes before adopting them. `policies/package-freshness.toml` records the
reviewed heads so the refresh gate is satisfied until this sweep is older than
24 hours or invalidated by package policy, package directories, checker logic,
or relevant source metadata changes. The freshness checker can be mechanically
current while update candidates remain open. The active dispositions for these
candidates live in `docs/maintainers/update-candidates.toml`; do not treat the
April 28 refresh as package-update closure.

Later on 2026-04-28, the llama.cpp runtime rebuild lane adopted upstream
`b8955` at `14e733e36f5752f39494b6c7e88022e43c05729a` for both
`llama.cpp-hip-gfx1151` and `llama.cpp-vulkan-gfx1151`. The `b8953..b8955`
range refactors speculative decoding parameters, switches server m-rope task
handling to `pos_next`, and updates argument parser, server, lookup,
speculative, and llama-bench sources; no local package patch carry changed.
`tools/amerge build llama.cpp-hip-gfx1151 llama.cpp-vulkan-gfx1151
lemonade-server` plan `96221b2d` completed with writable cache overrides and
produced `llama.cpp-hip-gfx1151-b8955-1-x86_64.pkg.tar.zst`,
`llama.cpp-vulkan-gfx1151-b8955-1-x86_64.pkg.tar.zst`, and the refreshed
`lemonade-server-10.2.0-5-x86_64.pkg.tar.zst` artifact with b8955 backend
metadata. `makepkg --verifysource` passed for both llama.cpp packages, and
`pytest tests/test_check_package_updates.py
packages/llama.cpp-hip-gfx1151/tests packages/llama.cpp-vulkan-gfx1151/tests
packages/lemonade-server/tests -q` reported `71 passed`. After privileged
deploy, `pacman -Q` reports
`llama.cpp-hip-gfx1151 b8955-1`, `llama.cpp-vulkan-gfx1151 b8955-1`, and
`lemonade-server 10.2.0-5`. The installed scenario run `python
tools/run_inference_scenarios.py --engine llama.cpp --engine lemonade --tag
smoke` passed 6/6 selected scenarios at run root
`docs/worklog/inference-runs/20260428T141728`: Lemonade CLI/server help,
Lemonade embedding and rerank pooling smokes, and both llama.cpp HIP/Vulkan
help scenarios.

Pull-request review follow-up bumped `lemonade-server` to `10.2.0-6` so the
metadata-only b8955 config change upgrades clients already on `10.2.0-5`.
`tools/amerge build lemonade-server` plan `20260428T142857-8440fea8` produced
`lemonade-server-10.2.0-6-x86_64.pkg.tar.zst`, and
`pytest packages/lemonade-server/tests -q` reported `2 passed`.

A follow-up live freshness check on 2026-04-28 found new actionable drift after
the b8955 build. Session-scoped prompts, specs, plans, scratch notes, and
handoff material belong in ignored locations such as `.agents/session/` or
`docs/worklog/`, with durable conclusions extracted into tracked docs. Upstream
llama.cpp moved to `b8958`;
the `b8955..b8958` range is CANN-focused plus a ggml backend/device
duplicate-registration guard and `-lm` link-behavior reversion. Lemonade
`10.3.0` is available with OmniRouter, a Tauri desktop app, the
`lemonade_server.service` to `lemond.service` rename, ROCm channel/default
changes, and system llama.cpp backend/version-tag config work that overlaps
local patch carry. ROCm PyTorch `release/2.11` moved to
`9413e9b96bcbeb8af1aa0280a3a9bc7dd048857e` with Windows test fixes and an
RDNA TunableOp test fix. AITER main moved to
`c1c65e6bef07a42bdf7e268f69b92e53f2e4ada5`, adding the previously tracked
communication-group and FlyDSL changes plus test determinism updates across
FP8, fused GEMM, MoE, normalization, rope, top-k, and gated-delta-rule tests.
Transformers has a GitHub `v5.7.0` tag while PyPI still reports `5.6.2`.
These are tracked in `docs/maintainers/update-candidates.toml`; do not treat
the b8955 build as full freshness closure.

The deploy for the TheRock metadata slices plus the Triton and AOCL-LibM
patch-carry slices was verified on the reference host on 2026-04-25. Installed
packages report `python-triton-gfx1151 3.0.0+git0ec280cf-1`,
`aocl-libm-gfx1151 5.2.2-1`, and the representative TheRock split packages
`rocm-core-gfx1151`, `rocm-debug-agent-gfx1151`,
`rocm-hip-libraries-gfx1151`, `rocm-ml-libraries-gfx1151`,
`rocm-opencl-runtime-gfx1151`, and `rocm-opencl-sdk-gfx1151` at
`7.13.0pre-5`. `rocm-debug-agent-gfx1151` provides and replaces
`rocr-debug-agent`; `rocm-opencl-runtime-gfx1151` provides `opencl-driver`,
does not claim the ICD loader, and depends on `opencl-icd-loader`; and stale
`hiptensor-gfx1151` / `rpp-gfx1151` installs remain absent. The installed
Triton package imports successfully and `repr(AttrsDescriptor())` round-trips
through `AttrsDescriptor.from_dict(...)`. `/usr/lib/libalm.so` has RUNPATH
`/usr/lib` and a `NEEDED` edge on `libau_cpuid.so`.

The `python-flash-attn-rocm-gfx1151` package experiment now tracks ROCm
FlashAttention `main_perf` commit `3f94643fb41bcedded28c85185a8e11d42ef1592`
with package version `2.8.4`. The package builds the Triton AMD path with
`FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`,
`FLASH_ATTENTION_SKIP_CUDA_BUILD=TRUE`, `FLASH_ATTENTION_FORCE_BUILD=TRUE`,
and `GPU_ARCHS=gfx1151`, skips upstream setup's bundled `third_party/aiter`
install in favor of `python-amd-aiter-gfx1151`, imports `amdsmi` before
FlashAttention reaches `torch`, and relaxes wheel metadata from
`triton==3.5.1` to `triton` so Arch dependencies stay on
`python-triton-gfx1151`.

On 2026-04-22, `tools/amerge build python-flash-attn-rocm-gfx1151` produced
`python-flash-attn-rocm-gfx1151 2.8.4-1`, and `tools/amerge deploy
python-flash-attn-rocm-gfx1151` installed it on the reference host. `pacman -Q
python-flash-attn-rocm-gfx1151` reports `2.8.4-1`. Installed import with
`FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE` reports `flash_attn_version 2.8.4`,
`use_triton_rocm True`, and backend module
`aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2`.
The tracked installed scenarios `flash-attn.triton-amd.backend-import` and
`flash-attn.triton-amd.qkvpacked-tiny` passed from
`python tools/run_inference_scenarios.py --engine flash-attn --tag smoke` at
run root `docs/worklog/inference-runs/20260422T200347`. The bounded GPU smoke
ran `flash_attn_qkvpacked_func` on a `(1, 16, 3, 2, 32)` float16 CUDA tensor,
returned shape `(1, 16, 2, 32)`, and reported finite output. Keep vLLM or
Transformers promotion behind an installed-engine backend-selection proof.

The first vLLM consumer backend-selection gate passed on the reference host. On
2026-04-23, `tools/amerge build python-vllm-rocm-gfx1151` built
`python-vllm-rocm-gfx1151 0.19.1-4` with
`0014-rocm-detect-flash-attn-triton-interface.patch`, which teaches vLLM's ROCm
platform probe to detect the local `flash_attn.flash_attn_interface` Triton AMD
binding when `FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`. `pacman -Q
python-vllm-rocm-gfx1151` reports `0.19.1-4`.

The tracked consumer scenario `vllm.flash-attn.triton-amd.vit-wrapper` passed
from `python tools/run_inference_scenarios.py --scenario
vllm.flash-attn.triton-amd.vit-wrapper` at run root
`docs/worklog/inference-runs/20260423T004320`. The scenario selected vLLM's ViT
`FLASH_ATTN` wrapper, printed `Using Flash Attention (Triton backend) for ViT
model on RDNA`, confirmed backend module
`aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2`, returned
shape `(1, 16, 2, 32)`, and reported finite output. Keep broader
FlashAttention consumer claims behind a real model route that actually selects
and validates this installed backend.

The first FlashAttention CK package lane is installed-validated. On
2026-04-23, `tools/amerge build python-flash-attn-rocm-gfx1151` completed plan
`2697cc6b` and produced `python-flash-attn-rocm-gfx1151 2.8.4-2`; `pacman -Q
python-flash-attn-rocm-gfx1151` reports `2.8.4-2`. The CK lane uses ROCm
FlashAttention `main_perf` commit
`3f94643fb41bcedded28c85185a8e11d42ef1592`, carries the setup.py portion of
ROCm/flash-attention branch `matthias.gfx1151_ck` commit
`561341f7e0913fb7dd12c81d9e68501a5a847220`, checks out
`csrc/composable_kernel` at `03ce21ddcbb75c5ac8630628a913d0b2ced4979a`, and
limits the initial build to a forward-only `OPT_DIM=32` CK smoke surface.
`flash-attn.ck.backend-import` passed at run root
`docs/worklog/inference-runs/20260423T033602`, selecting backend module
`flash_attn_2_cuda` with `use_triton_rocm False`.
`flash-attn.ck.qkvpacked-tiny` passed at run root
`docs/worklog/inference-runs/20260423T071523`, returning finite
`(1, 16, 2, 32)` output. Keep CK engine-integration claims pending until an
installed engine route selects this backend.

The current CK artifact, `python-flash-attn-rocm-gfx1151 2.8.4-10`, is now
installed-validated. `pacman -Q python-flash-attn-rocm-gfx1151` reports
`2.8.4-10`, and `flash-attn.ck.backend-import`,
`flash-attn.ck.qkvpacked-tiny`, `flash-attn.ck.varlen-tiny`,
`flash-attn.ck.varlen-tiny-d256`, and `flash-attn.ck.varlen-paged-kv` passed at
run root `docs/worklog/inference-runs/20260423T223607`. The installed direct CK
surface selected `flash_attn_2_cuda` with `use_triton_rocm False`; the bounded
direct smokes cover qkvpacked, variable-length d32, variable-length d256, and a
small direct paged-KV shape.

The tracked exploratory scenario `vllm.qwen3_5.0_8b.text.flash-attn-ck`
records the current vLLM consumer boundary. With
`python-vllm-rocm-gfx1151 0.19.1-6` and
`python-flash-attn-rocm-gfx1151 2.8.4-10` installed, it confirms the local
package selects CK (`flash_attn_2_cuda` with
`FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE`), reports FlashAttention version 2,
accepts vLLM's paged-KV varlen wrapper keywords, and reaches `llm_init_ok`.
It remains an expected blocked kernel probe: the normal Qwen3.5 hybrid path
presents `k_shape=(69080, 64, 2, 256)` to CK, so CK rejects the paged-KV page
with `Paged KV cache block size must be divisible by 128`. The tracked expected
blocked scenario passed without a diagnostic block-size override at run root
`docs/worklog/inference-runs/20260423T224553`. Diagnostics that forced a
128-divisible effective page reached
`k_shape=(6906, 640, 2, 256)` or `k_shape=(11513, 384, 2, 256)` and then
faulted the GPU inside CK. Treat the next engine step as upstream CK paged-KV
kernel work or a different validated backend, not as a local vLLM adapter
gap.

The durable closeout for that tabled unlock attempt is
`docs/maintainers/flashattention-ck-paged-kv.md`. It records the source
disposition, direct CK tests that passed, the blocked Qwen scenario, unsafe
workarounds, and the reference-match gates required before reopening the lane.

## Live Host State

The first full live cutover and subsequent native package rebuild completed
successfully on the reference Arch host.

The reference host's active Hugging Face cache root for current validation work
is `HF_HOME=/var/cache/hf`. Keep durable docs on model IDs and runtime
`--model-path` bindings, not committed cache snapshot subpaths. Current local
non-GGUF model IDs relevant to this branch are:

- `google/gemma-4-31B-it`
- `Qwen/Qwen3.5-0.8B`
- `Qwen/Qwen3.6-35B-A3B`
- `Qwen/Qwen3.6-35B-A3B-FP8`
- `jinaai/jina-reranker-v3`

Use `Qwen/Qwen3.6-35B-A3B-FP8` as the main Qwen MoE/shared-expert target for
this dev arc; it replaces the earlier Qwen3.5 122B-A10B testing and usage
target. Use `Qwen/Qwen3.6-35B-A3B` as the unquantized no-AITER control before
classifying FP8-specific failures. Both local Qwen3.6 configs advertise
`Qwen3_5MoeForConditionalGeneration` / `qwen3_5_moe`, so the maintained
Qwen3.5/GDN package carry is still relevant to this lane. The FP8 model
remains a target and blocked-probe lane, not an accepted passing smoke lane,
because the rebuilt native stack reproduces the expected Qwen3.6 FP8 probe
failures in the revalidation ledger.

The `intfloat/multilingual-e5-small` vLLM pooling embedding scenario passed on
2026-04-21 with `HF_HOME=/var/cache/hf`, ROCm `FLEX_ATTENTION`, and
`vllm.pooling.multilingual-e5-small.embeddings`; the tracked run completed in
`28.677313` seconds with finite embedding vectors and the fixed related-passage
ranking fixture. Keep tracked scenarios on model IDs plus runtime
`--model-path` bindings rather than new committed cache snapshot paths.

The Jina v3 reranker lane is a blocked vLLM pooling probe, not a passing
rerank smoke. Keep `vllm.pooling.jina-reranker-v3.rerank` on explicit
classification pooling (`--convert classify` / `PoolerConfig(task="classify")`)
so vLLM does not auto-convert the Qwen3-based checkpoint to an embedding
model. The current upstream model shape remains incompatible with vLLM's
linear sequence-classification conversion: the model card identifies local
inference as Transformers remote code, and its `JinaForRanking` class uses a
projector plus cosine scoring over query/document embed tokens. On the
reference host with vLLM `0.19.1`, the corrected vLLM probe reaches
`TransformersForSequenceClassification` conversion and then fails during load
because `model.lm_head.weight` and `score.weight` are not initialized from the
checkpoint. Do not treat this as a ROCm/FlexAttention failure, and do not
promote the scenario to a passing vLLM smoke unless vLLM gains support for
this remote-code ranking head or the lane switches to a vLLM-supported
cross-encoder model.

Lemonade has conventional embedding and reranking endpoints for registered
`llamacpp` models, and the tracked Lemonade pooling scenarios now cover both.
On 2026-04-21 the downloaded `user.zembed-1-Q4_K_M-GGUF-Q4_K_M` registration
passed through `/api/v1/embeddings`, returned three finite 2560-dimensional
vectors, and completed `lemonade.pooling.zembed-1-q4-k-m.embeddings`. The
downloaded `user.bge-reranker-v2-m3-Q8_0-GGUF` registration passed through
`/api/v1/reranking`, returned three finite scores, and produced the fixed
Paris, Berlin, unrelated ordering in
`lemonade.pooling.bge-reranker-v2-m3.rerank`. A prior MiniLM GGUF embedding
probe returned `Pooling type 'none' is not OAI compatible`; keep zembed-1 as
the current passing Lemonade embedding endpoint smoke.

The ZeroEntropy target models are covered by Hugging Face model-ID scenarios
rather than the Lemonade GGUF registrations. `transformers.zeroentropy.zembed-1.embeddings`
passed on 2026-04-21 with the cached `zeroentropy/zembed-1` model bound at
runtime by `--model-path`, finite normalized vectors, and a backpropagation
related-passage ranking fixture. `transformers.zeroentropy.zerank-2.rerank`
passed on the same host with the cached `zeroentropy/zerank-2` model bound at
runtime, finite Yes-logit scores, and the model-card arithmetic ranking
fixture. The helper uses Transformers directly because these model cards
document `SentenceTransformer` and `CrossEncoder` usage, while Lemonade's
documented local endpoints require registered `llamacpp` or `flm` recipes for
embeddings and `llamacpp` for reranking.

The rebuilt installed stack passed the unquantized Qwen3.6 control on
2026-04-20 with `HF_HOME=/var/cache/hf` and `Qwen/Qwen3.6-35B-A3B`,
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

Reduced OpenAI-compatible Qwen3.6 server scenarios now exist for reasoning,
reasoning-disabled, MTP, tool calling, benchmark-lite, advanced selectors,
long-context-reduced, and media-embedding flows. All eight reduced server
scenarios are validated; the first six passed on 2026-04-20:

- `vllm.qwen3_6.35b-a3b.server.reasoning` completed in `132.196358` seconds
  with `server_ready`, `reasoning_ok`, `reasoning_parser qwen3`, `Using TRITON
  backend for Unquantized MoE`, `Available KV cache memory: 12.31 GiB`, and a
  populated OpenAI-compatible `reasoning` field.
- `vllm.qwen3_6.35b-a3b.server.reasoning-disabled` completed in `106.799851`
  seconds with `server_ready`, `reasoning_disabled_ok`, and no populated
  reasoning field.
- `vllm.qwen3_6.35b-a3b.server.tool` completed in `115.812169` seconds with
  `server_ready`, `--enable-auto-tool-choice`, `--tool-call-parser
  qwen3_coder`, a `get_weather` tool call, a tool-response follow-up, and
  `tool_ok`.
- `vllm.qwen3_6.35b-a3b.server.benchmark-lite` completed in `96.436773`
  seconds with `server_ready` and `benchmark_lite_ok`; this is correctness
  coverage only, not a throughput measurement.
- `vllm.qwen3_6.35b-a3b.server.advanced-selectors` completed in `109.937614`
  seconds with `server_ready`, `advanced_selectors_ok`,
  `--max-num-batched-tokens 8192`, `--max-num-seqs 256`, and `Available KV
  cache memory: 9.91 GiB`.
- `vllm.qwen3_6.35b-a3b.server.long-context-reduced` completed in
  `112.418584` seconds with `server_ready` and `long_context_reduced_ok`; the
  full 1,010,000-token YaRN shape remains advisory-only.

The two remaining reduced scenarios passed after targeted root-cause fixes on
2026-04-21:

- `vllm.qwen3_6.35b-a3b.server.mtp` first completed in `112.647863` seconds
  with the non-padded workaround. The root fix is now installed as
  `python-vllm-rocm-gfx1151` `0.19.1-2`: the system-package rerun completed in
  `119.066554` seconds with `server_ready`, `mtp_ok`, `--speculative-config
  {"method":"mtp","num_speculative_tokens":2}`, no
  `disable_padded_drafter_batch` workaround, `Using TRITON backend for
  Unquantized MoE`, `Available KV cache memory: 8.26 GiB`, and the padded
  EAGLE/MTP drafter `valid_count` typing patch.
- `vllm.qwen3_6.35b-a3b.server.media-embedding` completed in `112.851312`
  seconds with `server_ready`, `media_embedding_ok`, `Using
  AttentionBackendEnum.TORCH_SDPA for MMEncoderAttention`, `Using TRITON backend
  for Unquantized MoE`, `Available KV cache memory: 11.44 GiB`, and structured
  `--limit-mm-per-prompt {"audio":0,"image":{"count":1,"height":2,"width":2},"video":0}`.
  The previous media failure was isolated to unbounded Qwen3 VL dummy image
  profiling, which attempted a `256.00 GiB` allocation before `server_ready`.

An additional one-off speculative decoding sweep on 2026-04-21 found one more
locally viable method for the reduced Qwen3.6 server shape:

- `ngram_gpu` with `--speculative-config
  {"method":"ngram_gpu","num_speculative_tokens":2,"prompt_lookup_min":2,"prompt_lookup_max":5}`
  started the OpenAI-compatible server and returned a valid chat completion in
  `106.56` seconds with thinking disabled.
- CPU `ngram` with the same prompt lookup settings started the server but
  killed `EngineCore` during generation and returned HTTP 500, both with
  thinking enabled and disabled; no Python root-cause traceback was emitted
  before `EngineDeadError`.
- `draft_model` using `Qwen/Qwen3.5-0.8B` did not behave as a plain two-model
  draft path in this vLLM build. vLLM remapped the draft checkpoint to
  `Qwen3_5MTP`, then failed loading the draft weights with `The size of tensor
  a (2048) must match the size of tensor b (1024) at non-singleton dimension 1`.
- forcing `eagle` or `eagle3` with `Qwen/Qwen3.5-0.8B` is not a valid local
  EAGLE test; both configurations failed during `EAGLEConfig` construction
  with `AttributeError: 'Qwen3_5Config' object has no attribute 'vocab_size`.
- `suffix` failed at config validation because `arctic-inference==0.1.1` is
  not installed.

Installed and validated at least once on the live host:

- generated TheRock/ROCm split package family
- AOCL layer
- optimized `python-gfx1151`
- rebuilt wheel layer
- Triton and AOTriton
- PyTorch, TorchVision, AITER, and vLLM
- `vllm.qwen3_6.35b-a3b.server.reasoning`
- `vllm.qwen3_6.35b-a3b.server.reasoning-disabled`
- `vllm.qwen3_6.35b-a3b.server.tool`
- `vllm.qwen3_6.35b-a3b.server.benchmark-lite`
- `vllm.qwen3_6.35b-a3b.server.advanced-selectors`
- `vllm.qwen3_6.35b-a3b.server.long-context-reduced`
- `vllm.qwen3_6.35b-a3b.server.mtp`
- `vllm.qwen3_6.35b-a3b.server.media-embedding`
- `llama.cpp` HIP and Vulkan backends
- Lemonade server/app/meta packages

Current installed native package state, checked on 2026-04-20 after the full
`amerge` run completed and refreshed on 2026-04-22 for the llama.cpp/Lemonade
package updates:

- `aocl-libm-gfx1151` tracks upstream AOCL-LibM `5.2.2` and built
  successfully after installing host build dependency `scons`. The scaffold
  uses Arch's system `scons` directly and passes resolved compiler paths to
  AOCL-LibM's SCons variables rather than using the recipe's venv-local pip
  bootstrap.
- `llama.cpp-hip-gfx1151` and `llama.cpp-vulkan-gfx1151` package definitions
  track upstream llama.cpp `b8911` at commit
  `5d2b52d80d9f375a6e81d07e212d047d8ee4f76e`. The live host reports
  `llama.cpp-hip-gfx1151 b8911-1` and
  `llama.cpp-vulkan-gfx1151 b8911-1`.
  The Vulkan package metadata still includes `spirv-headers`.
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
  `python-vllm-rocm-gfx1151 0.19.1-2`.
- `python-triton-gfx1151` package-manager metadata and Python wheel metadata
  now agree: pacman reports `3.0.0+git0ec280cf-1`, while
  `importlib.metadata.version("triton")` reports `3.0.0+git0ec280cf`.
- `lemonade-server` package metadata points its system-managed llama.cpp
  backends at `b8911`; the live host reports `lemonade-server 10.2.0-5`.

## Live Smoke Coverage

This section includes both current installed-host checks and historical smoke
records. When a result was recorded before the 2026-04-20 rebuild boundary,
the rebuild revalidation ledger records whether that result was promoted or
retired.

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
- On 2026-04-22, after deploying `llama.cpp-hip-gfx1151 b8881-1`,
  `llama.cpp-vulkan-gfx1151 b8881-1`, and `lemonade-server 10.2.0-3`,
  `python tools/run_inference_scenarios.py --engine llama.cpp --engine lemonade --tag smoke`
  passed 6/6 selected scenarios: Lemonade CLI/server help, Lemonade embedding
  and rerank pooling smokes, and both llama.cpp HIP/Vulkan help scenarios. The
  run root was `docs/worklog/inference-runs/20260422T003259`.
- On 2026-04-22, after deploying `llama.cpp-hip-gfx1151 b8892-1`,
  `llama.cpp-vulkan-gfx1151 b8892-1`, and `lemonade-server 10.2.0-4`,
  `python tools/run_inference_scenarios.py --engine llama.cpp --engine lemonade --tag smoke`
  passed the same 6/6 selected scenarios. The run root was
  `docs/worklog/inference-runs/20260422T211346`.
- On 2026-04-23, after deploying `llama.cpp-hip-gfx1151 b8911-1`,
  `llama.cpp-vulkan-gfx1151 b8911-1`, and `lemonade-server 10.2.0-5`,
  `python tools/run_inference_scenarios.py --engine llama.cpp --engine lemonade --tag smoke`
  passed the same 6/6 selected scenarios. The run root was
  `docs/worklog/inference-runs/20260423T221640`.
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
    scenarios against `google/gemma-4-26B-A4B-it` through the runtime cache
    binding;
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
  - before the self-hosted rebuild, leaving `video` implicit in
    `--limit-mm-per-prompt` was enough to send vLLM back into multimodal warmup
    on this host and reproduce the older GPU memory-access fault during engine
    initialization
  - the questioned carries are now split cleanly by evidence:
    - keep the AITER fused-MoE experiment guards:
      `python-amd-aiter-gfx1151/0003-fused-moe-unknown-gfx-falls-back-to-2stage.patch`,
      `python-amd-aiter-gfx1151/0004-moe-tuner-skips-missing-1stage-asm-metadata.patch`,
      and
      `python-amd-aiter-gfx1151/0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch`;
      on 2026-04-20, package-local tests passed `10 passed`, including
      unknown-gfx fallback, missing 1-stage ASM metadata handling, and
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
  first compiled, MoE, TorchAO, forced-attention, and representative
  multimodal decisions are now recorded; keep the remaining multimodal modes
  exploratory until each mode has its own reference-host pass.
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
    during server/AsyncLLM initialization with a ROCm GPU memory-access fault;
    this was later retired by the 2026-04-20 self-hosted rebuild revalidation
  - an isolated E2B server basic rerun reproduced the same fault before the
    rebuild, while a direct offline eager E2B text smoke passed and returned
    `The quick brown fox jumps.`
  - an explicit pre-rebuild `--attention-backend TRITON_ATTN` E2B server probe
    proved vLLM selected `Using TRITON_ATTN backend` and still hit the same GPU
    memory-access fault, so the stale-stack E2B server fault was not explained
    by AITER unified attention alone
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
- The 2026-04-20 rebuilt-stack E2B server revalidation retires the old
  server/AsyncLLM initialization fault:
  - `vllm.gemma4.e2b.server.basic` passed in `45.623171` seconds with
    `--enforce-eager`, text-only multimodal limits, `ROCM_AITER_UNIFIED_ATTN`,
    and `basic_ok`
  - `vllm.gemma4.e2b.server.attn-triton` passed in `44.833574` seconds with
    explicit `--attention-backend TRITON_ATTN`, text-only multimodal limits,
    `Using TRITON_ATTN backend`, and `basic_ok`
  - the forced Triton-attention pass also revalidates the carried large-head
    Triton unified-attention tile reduction as the current accepted guard for
    the gfx1151 64 KiB LDS overflow
  - `vllm.gemma4.e2b.server.image` passed in `59.030087` seconds with
    `ROCM_AITER_UNIFIED_ATTN`, encoder-cache profiling, a completed
    multi-modal warmup in `0.493s`, an HTTP 200 image request, response text
    `Solid bright blue color.`, and `image_ok`
  - the image scenario required a smoke-helper fix, not a package-runtime
    patch: the embedded PNG data URL was corrupt, and image caption validation
    needed to accept a nonempty descriptive caption instead of reusing the
    exact-five-word text smoke assertion
  - only the image-input E2B multimodal path is represented by this pass; keep
    multi-image, dynamic image, audio, video, and multimodal-tool scenarios
    exploratory until each has its own run
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
    against `google/gemma-4-31B-it`
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
    `python-vllm-rocm-gfx1151 0.19.1-2`; use the revalidation ledger before
    treating earlier Gemma 4 and Qwen scenario results as accepted evidence for
    the current installed stack
  - after pkgrel `-26` was installed, the existing Gemma 4 26B-A4B
    installed-host lane still passed with the package:
    `vllm.gemma4.26b-a4b.text.basic` passed in `195.710255` seconds, and
    `vllm.gemma4.26b-a4b.server.basic` passed in `309.115382` seconds against
    the older local cache binding for `google/gemma-4-26B-A4B-it`;
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
    this finding on 2026-04-20 in `22.765256` seconds against
    `Qwen/Qwen3.6-35B-A3B-FP8`, with `config_quantization_config_present true`
    and the same backend-selection error.
  - The 2026-04-20 rebuilt-stack control for `Qwen/Qwen3.6-35B-A3B` passed
    unquantized with AITER disabled, `--max-num-batched-tokens 32`, and
    `--gpu-memory-utilization 0.9`; the tracked scenario completed in
    `85.054242` seconds and generated `ready`. Treat this as the current
    same-family control when comparing FP8-specific failures.
  - the new compiled same-family control
    `vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-compiled` passed on
    2026-04-20 in `147.699736` seconds with fresh compile caches,
    `enforce_eager=False`, `Using Triton/FLA GDN prefill kernel`,
    `Using TRITON backend for Unquantized MoE`, `Using ROCM_ATTN backend`,
    `torch.compile took 22.75 s in total`, graph capture in 6 seconds, output
    `ready`, and `basic_ok`
  - the Qwen3.6 compiled control still logged the same non-fatal
    `Cannot use ROCm custom paged attention kernel, falling back to Triton implementation`
    marker and underlying `operation scheduled before its operands`
    diagnostic seen in the smaller Qwen3.5 compiled probe; because generation
    completed, this remains a fallback diagnostic rather than a blocker for the
    tracked Qwen unquantized controls
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
  - The deeper upstream pass did not find a small upstream gfx11
    `mfma_adaptor` carry to backport. AITER v0.1.12 release notes list OPUS
    migration work and RDNA registration/config selection for gfx1150/1151,
    but the prebuilt kernel support in that release remains gfx942/gfx950, and
    the installed OPUS header still has only the gfx9 MFMA adaptor and gfx1250
    WMMA adaptor choices for this code path. Treat a gfx11 OPUS FP8 adaptor as
    new kernel feature work unless upstream lands it.
  - Task 4 quantization-lane coverage now includes three additional tracked
    exploratory probes under `inference/scenarios/vllm-qwen.toml`:
    `vllm.qwen3.0_6b-fp8-kv.text.fp8-dense-quark`,
    `vllm.qwen2_5.0_5b-gptq-int4.text.basic`, and
    `vllm.qwen3_5.2b-nvfp4.text.unsupported-rocm-gfx1151`.
    The dense FP8 lane uses an AMD Quark-exported Qwen3 FP8 checkpoint with
    `quantization="quark"` and `kv_cache_dtype="fp8"`. The GPTQ-Int4 lane uses
    the small official Qwen2.5 GPTQ-Int4 checkpoint with `dtype="float16"`,
    matching vLLM's GPTQ activation dtype contract. Both are expected runnable
    probes, but not promoted smokes until they pass on the reference host.
  - The AxionML NVFP4 probe is expected to fail on ROCm/gfx1151 with
    `modelopt_fp4 quantization is currently not supported in rocm.` The
    checkpoint is ModelOpt NVFP4, so the scenario uses `modelopt_fp4` and fails
    in the local vLLM ROCm platform quantization gate before Petit NVFP4 backend
    selection is relevant. Petit is not a current gfx1151 answer: its published
    support target is AMD CDNA2/CDNA3, so it is useful evidence for MI-class
    hardware, not a Strix Halo/RDNA 3.5 package patch.
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
    `--source-model <model-id-or-path>` loads the source in BF16, applies
    TorchAO int8 weight-only quantization only to the Gemma 4 language model,
    saves TorchAO safetensors plus processor or tokenizer files, and runs a
    tokenizer-backed vLLM generation pass; use `--dry-run` first to inspect
    the chosen quantized output directory and execution mode.
  - keep the real-model serialized path language-only. Full-model TorchAO
    serialization quantizes HF-managed multimodal tower weights such as
    `vision_tower.patch_embedder.input_proj.weight`; vLLM instantiates those
    towers as plain HF parameters, so loading an `Int8Tensor` there fails
    during `copy_` with
    `AttributeError: 'Tensor' object has no attribute 'tensor_data_names'`.
    The helper now writes those multimodal weights as BF16 `Tensor` entries
    while keeping language projection weights as TorchAO `Int8Tensor` entries.
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
  - the refreshed backend table identifies the packaged backends explicitly as:
    - `System llama-server-hip-gfx1151 llama.cpp b8911`
    - `System llama-server-vulkan-gfx1151 llama.cpp b8911`

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
  - the post-rebuild `shlex.split(CMAKE_ARGS)` probe no longer reproduces the
    earlier gfx1151 `csrc/sampler.hip` compiler failure
  - on 2026-04-20, a focused `makepkg -ef --noarchive --nocheck` run with a
    nested quoted `CMAKE_HIP_FLAGS` value containing `--offload-arch=gfx1151`,
    `-mllvm -amdgpu-function-calls=false`,
    `-mllvm -amdgpu-early-inline-all=true`, and `-famd-opt` completed
    successfully and produced the vLLM wheel/package directory
  - keep the committed direct `CFLAGS`/`CXXFLAGS`/`HIPFLAGS` forwarding patch;
    treat quoted `CMAKE_ARGS` parsing as optional build plumbing, not as a
    retained runtime-finding patch
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
    `vllm.gemma4.e2b.torchao.online-real-model` passed after the self-hosted
    rebuild on 2026-04-20 in `58.446559` seconds with
    `using_online_source_model`, `quantization=torchao`, `enforce_eager=True`,
    `ROCM_AITER_UNIFIED_ATTN`, 10.62 GiB model-loading memory, `llm_init_ok`,
    and `generation_ok`; the serialized
    `vllm.gemma4.e2b.torchao.real-model` scenario passed on 2026-04-21 in
    `76.655479` seconds with `prepare_real_ok`, `skip_quantized_modules`,
    `quantized_patterns`, `quantization=torchao`, `enforce_eager=True`,
    `llm_init_ok`, and `generation_ok`.
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
