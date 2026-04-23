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

`FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE` remains the explicit runtime selector
for the packaged Triton AMD path through repo-owned AITER. Treat
`FLASH_ATTENTION_TRITON_AMD_AUTOTUNE=TRUE` as a later performance experiment.

## Local Boundaries

- Depends on repo-owned `python-amd-aiter-gfx1151`,
  `python-triton-gfx1151`, and `python-pytorch-opt-rocm-gfx1151`.
- Skips FlashAttention setup's bundled `third_party/aiter` install because
  AITER is packaged and patched separately in this repo.
- Relaxes upstream wheel metadata from `triton==3.5.1` to `triton` so the
  Arch package dependency stays on `python-triton-gfx1151`.
- Imports `amdsmi` before FlashAttention reaches `torch`, matching the local
  ROCm import-order guard used elsewhere in the stack.

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
python tools/run_inference_scenarios.py --scenario flash-attn.ck.qkvpacked-tiny
```

Keep any CK engine-integration scenario exploratory until an installed engine
proves it can route to this backend. Keep Triton AMD validation explicit because
runtime backend selection still depends on `FLASH_ATTENTION_TRITON_AMD_ENABLE`.

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
