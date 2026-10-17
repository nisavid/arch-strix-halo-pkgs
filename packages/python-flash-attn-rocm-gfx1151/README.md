# python-flash-attn-rocm-gfx1151

This is the local FlashAttention package experiment for Strix Halo `gfx1151`.
It follows the ROCm FlashAttention `main_perf` AMD backend lane at commit
`3f94643fb41bcedded28c85185a8e11d42ef1592`, which reports package version
`2.8.4`.

The package intentionally builds the ROCm CK extension with
`FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE`,
`FLASH_ATTENTION_SKIP_CUDA_BUILD=FALSE`, and `GPU_ARCHS=gfx1151`. It carries
the setup.py portion of ROCm/flash-attention branch `matthias.gfx1151_ck`
commit `561341f7e0913fb7dd12c81d9e68501a5a847220`, which adds `gfx1151` to
FlashAttention's CK architecture validation and passes the matching `gfx11`
target into CK FMHA codegen.

The package also prepares `csrc/composable_kernel` at
`03ce21ddcbb75c5ac8630628a913d0b2ced4979a`, the matching CK gitlink from that
branch. The older `main_perf` CK submodule does not expose `gfx11` FMHA codegen
factories.

AITER is not a build or runtime input on the CK path. With
`FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE`, `setup.py` takes its `ck` branch
(`ROCM_BACKEND = "ck"`); only the `triton` branch installs the bundled
`third_party/aiter`, and patch 0001 skips that install anyway. At runtime,
`flash_attn/flash_attn_interface.py` imports
`aiter.ops.triton._triton_kernels.flash_attn_triton_amd` only when
`FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`; otherwise it loads the CK
`flash_attn_2_cuda` extension, and no other `flash_attn` module references
AITER. The package therefore lists `python-amd-aiter-gfx1151` only as an
optional dependency.

`FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE` remains the explicit runtime selector
for the Triton AMD path, which needs `python-amd-aiter-gfx1151` installed.
Treat `FLASH_ATTENTION_TRITON_AMD_AUTOTUNE=TRUE` as a later performance
experiment.

## Local Boundaries

- Depends on repo-owned `python-triton-gfx1151` and
  `python-pytorch-opt-rocm-gfx1151`. The CK extension links libtorch, so
  every torch rebuild needs a FlashAttention rebuild.
- Lists repo-owned `python-amd-aiter-gfx1151` as an optional dependency for
  the Triton AMD backend only.
- Skips FlashAttention setup's bundled `third_party/aiter` install because
  AITER is packaged and patched separately in this repo.
- Relaxes upstream wheel metadata from `triton==3.5.1` to `triton` so the
  Arch package dependency stays on `python-triton-gfx1151`.
- Imports `amdsmi` before FlashAttention reaches `torch`, matching the local
  ROCm import-order guard used elsewhere in the stack.
- Initializes the CK split-KV forward args
  (`0010-init-ck-splitkv-args.patch`). The packaged CK commit added
  `sink_ptr`, `sink_size`, and `logits_soft_cap` to `fmha_fwd_splitkv_args`,
  and FlashAttention `3f94643f` never sets them. The patch value-initializes
  the struct and sets the three fields explicitly, backporting the split-KV
  hunks of upstream `8afc617a` (#2363) that patch 0007 left out.

## Validation Gates

The first CK package gate is build/import proof:

```sh
tools/amerge build python-flash-attn-rocm-gfx1151
```

After installation, the direct CK smoke should run before any engine
integration claim:

```sh
FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE python - <<'PY'
import torch
from flash_attn import flash_attn_qkvpacked_func

qkv = torch.randn(1, 16, 3, 2, 32, device="cuda", dtype=torch.float16)
out = flash_attn_qkvpacked_func(qkv, dropout_p=0.0, causal=False)
torch.cuda.synchronize()
print("shape", tuple(out.shape))
print("finite", bool(torch.isfinite(out).all().item()))
PY
```

The tracked scenario equivalent is:

```sh
python tools/run_inference_scenarios.py \
  --scenario flash-attn.ck.qkvpacked-tiny \
  --scenario flash-attn.ck.varlen-tiny
```

Keep any CK engine-integration scenario exploratory until an installed engine
proves it can route to this backend. vLLM's ROCm V1 `FLASH_ATTN` path currently
needs a vLLM-side adapter before it can consume upstream ROCm `flash_attn`
through the same call surface used by CUDA `vllm_flash_attn`. Keep Triton AMD
validation explicit because runtime backend selection still depends on
`FLASH_ATTENTION_TRITON_AMD_ENABLE`.

The 2026-05-26 PyTorch `2.12.0-2` rebuild lane bumps this package to
`2.8.4-12` so package-manager upgrades deliver the CK extension rebuilt against
the refreshed local torch headers. Keep the direct CK backend-import smoke as
the installed gate before claiming engine integration behavior.

The 2026-06-15 PyTorch `c7badbdf` runtime-base lane bumps this package to
`2.8.4-14` so it supersedes both the adopted 26872de/pkgrel-12 package and the
unmerged ab32a1f/pkgrel-13 host-drift artifact.

The 2026-09-25 W2A lane bumps this package to `2.8.4-15`. It rebuilds the CK
extension against `python-pytorch-opt-rocm-gfx1151 2.12.0-5` and the Python
3.14 foundation, and moves `python-amd-aiter-gfx1151` from `depends` to
`optdepends`. The source commit and patches 0001-0009 are unchanged.

The 2026-09-25 `2.8.4-16` release adds patch 0010, which fixes a GPU memory
fault in the paged-KV varlen path. `get_ck_fmha_varlen_fwd_splitkv_args()`
declared `fmha_fwd_splitkv_args args;` without initializing it, so CK read
leftover host stack contents as `sink_ptr` and dereferenced them in the
split-KV kernel whenever they were non-null. Rebuild, install, and rerun the
direct CK scenarios, including `flash-attn.ck.varlen-paged-kv`, before
claiming the fix on the reference host. The 2026-10-02 W2A-root gate under
Current Evidence passed three of them (`flash-attn.ck.backend-import`,
`flash-attn.ck.varlen-tiny` and `flash-attn.ck.varlen-paged-kv`) on
`2.8.4-16`, but the package is not installed on the reference host yet, so
that host gate stays open. Patch 0007 becomes redundant once the package
moves to a FlashAttention ref that contains upstream `8afc617a`.
Patch 0010 becomes redundant only when the target source sets `sink_ptr`,
`sink_size` and `logits_soft_cap` in both split-KV argument builders.
`8afc617a` sets only the sink fields and still declares `args;`
uninitialized, and `c661198a` sets `logits_soft_cap` in the varlen builder
only and is not an ancestor of `8afc617a`. If upstream still leaves `args`
uninitialized then, keep its value-initialization as a reduced local patch.

## Current Evidence

On 2026-04-22, `tools/amerge build python-flash-attn-rocm-gfx1151` built
`2.8.4-1`, and `tools/amerge deploy python-flash-attn-rocm-gfx1151` installed
it on the reference host. `pacman -Q python-flash-attn-rocm-gfx1151` reports
`2.8.4-1`. Installed import with `FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`
reports `flash_attn_version 2.8.4`, `use_triton_rocm True`, and backend module
`aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2`.

The tracked installed scenarios
`flash-attn.triton-amd.backend-import` and
`flash-attn.triton-amd.qkvpacked-tiny` passed from
`python tools/run_inference_scenarios.py --engine flash-attn --tag smoke` at
run root `docs/worklog/inference-runs/20260422T200347`. The bounded GPU smoke ran
`flash_attn_qkvpacked_func` on a `(1, 16, 3, 2, 32)` float16 CUDA tensor and
returned finite `(1, 16, 2, 32)` output.

On 2026-04-23, the CK package lane built
`python-flash-attn-rocm-gfx1151 2.8.4-2` with `tools/amerge` plan
`2697cc6b`. The build used the `gfx1151` CK codegen patch, the matching CK
submodule commit, and the reduced forward-only `OPT_DIM=32` kernel set.
`pacman -Q python-flash-attn-rocm-gfx1151` reports `2.8.4-2`.
`flash-attn.ck.backend-import` passed at run root
`docs/worklog/inference-runs/20260423T033602`, selecting
`flash_attn_2_cuda` with `use_triton_rocm False`.
`flash-attn.ck.qkvpacked-tiny` passed at run root
`docs/worklog/inference-runs/20260423T071523`, returning finite
`(1, 16, 2, 32)` output.

Later on 2026-04-23, `python-flash-attn-rocm-gfx1151 2.8.4-10` built and
installed with the bounded `OPT_DIM=32,256` CK surface plus direct
variable-length and paged-KV smokes. `pacman -Q
python-flash-attn-rocm-gfx1151` reports `2.8.4-10`. The installed scenarios
`flash-attn.ck.backend-import`, `flash-attn.ck.qkvpacked-tiny`,
`flash-attn.ck.varlen-tiny`, `flash-attn.ck.varlen-tiny-d256`, and
`flash-attn.ck.varlen-paged-kv` passed at run root
`docs/worklog/inference-runs/20260423T223607`; CK selected
`flash_attn_2_cuda` with `use_triton_rocm False`. The paged-KV pass relied on
undefined behaviour: before patch 0010, the split-KV args carried
uninitialized `sink_ptr`, `sink_size`, and `logits_soft_cap`, so that pass
only shows the stack happened to hold a null `sink_ptr` in that run.

The exploratory vLLM Qwen CK consumer probe is tracked as blocked, not passed.
It confirms that vLLM sees CK (`flash_attn_2_cuda` and
`FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE`) and reaches vLLM initialization, but
the normal Qwen3.5 hybrid path presents a 64-token paged-KV kernel page while
CK requires a 128-token multiple. Diagnostics that force 128-divisible pages
progress past that check and then fault the GPU inside CK. The expected blocked
scenario passed at run root `docs/worklog/inference-runs/20260423T224553`.
The durable closeout and future test gates are recorded in
`docs/maintainers/flashattention-ck-paged-kv.md`.

On 2026-10-02, the post-build gate set on #111 passed on `2.8.4-16` in the
isolated W2A build root, in one guarded GPU run with 0 GPU page faults. With
`FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE` and AITER absent from the root,
`flash-attn.ck.backend-import` selected `flash_attn_2_cuda` with
`use_triton_rocm False`, and `flash-attn.ck.varlen-tiny` and
`flash-attn.ck.varlen-paged-kv` returned finite output. This paged-KV
pass is on a build with patch 0010, so it does not depend on an uninitialized
`sink_ptr`. The package is built and validated in the W2A root only: it is
not deployed, installed-smoked, or validated on the reference host.
`docs/maintainers/current-state.md` records the run.
