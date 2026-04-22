# python-flash-attn-rocm-gfx1151

This is the local FlashAttention package experiment for Strix Halo `gfx1151`.
It follows the ROCm FlashAttention `main_perf` Triton backend lane at commit
`3f94643fb41bcedded28c85185a8e11d42ef1592`, which reports package version
`2.8.4`.

The package intentionally builds the ROCm Triton path with
`FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`, `FLASH_ATTENTION_SKIP_CUDA_BUILD=TRUE`,
and `GPU_ARCHS=gfx1151`. `FLASH_ATTENTION_TRITON_AMD_AUTOTUNE=TRUE` remains a
later performance experiment after the non-autotuned direct smoke passes.

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

The first package gate is build/import proof:

```sh
tools/amerge build python-flash-attn-rocm-gfx1151
```

After installation, the direct Triton AMD smoke should run before any vLLM or
Transformers integration claim:

```sh
FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE python - <<'PY'
import torch
from flash_attn import flash_attn_qkvpacked_func

qkv = torch.randn(1, 16, 3, 2, 32, device="cuda", dtype=torch.float16)
out = flash_attn_qkvpacked_func(qkv, dropout_p=0.0, causal=False)
torch.cuda.synchronize()
print("shape", tuple(out.shape))
print("finite", bool(torch.isfinite(out).all().item()))
PY
```

Keep any vLLM scenario exploratory until direct `flash_attn` import and
bounded Triton AMD tests pass on the reference host.

## Current Evidence

On 2026-04-22, `tools/amerge build python-flash-attn-rocm-gfx1151` built
`2.8.4-1`. A staged import from the built package image selected
`aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2` with
`FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`. A bounded host GPU smoke from the
built image ran `flash_attn_qkvpacked_func` on a `(1, 16, 3, 2, 32)` float16
CUDA tensor and returned finite `(1, 16, 2, 32)` output.

The install gate is still pending:

```sh
tools/amerge deploy python-flash-attn-rocm-gfx1151
```
