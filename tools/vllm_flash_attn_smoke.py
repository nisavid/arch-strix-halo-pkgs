#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import sys


_VALIDATED_BACKEND_MODULE_PREFIX = (
    "aiter.ops.triton._triton_kernels.flash_attn_triton_amd"
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded vLLM consumer smokes for ROCm FlashAttention."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("vit-wrapper",),
        help="which vLLM FlashAttention consumer path to run",
    )
    parser.add_argument("--batch-size", type=_positive_int, default=1)
    parser.add_argument("--seqlen", type=_positive_int, default=16)
    parser.add_argument("--heads", type=_positive_int, default=2)
    parser.add_argument("--head-dim", type=_positive_int, default=32)
    parser.add_argument("--seed", type=int)
    return parser


def _is_finite(torch, tensor) -> bool:
    finite_value = torch.isfinite(tensor).all()
    if hasattr(finite_value, "item"):
        return bool(finite_value.item())
    return bool(finite_value)


def _flash_attn_backend() -> tuple[object, object]:
    flash_attn = importlib.import_module("flash_attn")
    wrapper = getattr(flash_attn, "flash_attn_interface", None)
    if wrapper is None:
        raise RuntimeError("flash_attn.flash_attn_interface missing")
    if getattr(wrapper, "USE_TRITON_ROCM", False) is not True:
        raise RuntimeError("flash_attn.flash_attn_interface USE_TRITON_ROCM != True")
    backend = getattr(wrapper, "flash_attn_gpu", None)
    if backend is None:
        raise RuntimeError("flash_attn.flash_attn_interface.flash_attn_gpu missing")
    backend_name = getattr(backend, "__name__", "")
    if not backend_name.startswith(_VALIDATED_BACKEND_MODULE_PREFIX):
        raise RuntimeError(
            "flash_attn.flash_attn_interface.flash_attn_gpu "
            f"{backend_name} does not start with {_VALIDATED_BACKEND_MODULE_PREFIX}"
        )
    return wrapper, backend


def _run_vit_wrapper(args: argparse.Namespace) -> int:
    try:
        torch = importlib.import_module("torch")
        from vllm.platforms.rocm import RocmPlatform
        from vllm.v1.attention.ops.vit_attn_wrappers import vit_flash_attn_wrapper
    except (ImportError, ModuleNotFoundError, RuntimeError, AttributeError) as exc:
        print(f"vllm_flash_attn_import_error {exc}")
        return 1

    try:
        wrapper, backend = _flash_attn_backend()
    except (ImportError, ModuleNotFoundError, RuntimeError, AttributeError) as exc:
        print(f"vllm_flash_attn_backend_error {exc}")
        return 1

    if not torch.cuda.is_available():
        print("cuda_available False")
        return 1

    selected_backend = RocmPlatform.get_vit_attn_backend(
        args.head_dim,
        torch.float16,
    )
    selected_name = getattr(selected_backend, "name", str(selected_backend))
    print("mode vit-wrapper")
    print(f"use_triton_rocm {bool(getattr(wrapper, 'USE_TRITON_ROCM', False))}")
    print(f"backend_module {backend.__name__}")
    print(f"backend_file {getattr(backend, '__file__', 'unknown')}")
    print(f"vit_backend {selected_name}")
    if selected_name != "FLASH_ATTN":
        return 1

    if args.seed is not None:
        torch.manual_seed(args.seed)

    shape = (args.batch_size, args.seqlen, args.heads, args.head_dim)
    q = torch.randn(shape, dtype=torch.float16, device="cuda")
    k = torch.randn(shape, dtype=torch.float16, device="cuda")
    v = torch.randn(shape, dtype=torch.float16, device="cuda")
    output = vit_flash_attn_wrapper(
        q,
        k,
        v,
        args.batch_size,
        False,
        None,
    )
    torch.cuda.synchronize()
    finite = _is_finite(torch, output)

    print(f"shape {tuple(output.shape)}")
    print(f"finite {finite}")
    if tuple(output.shape) != shape or not finite:
        return 1
    print("vllm_flash_attn_vit_ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "vit-wrapper":
        return _run_vit_wrapper(args)
    raise AssertionError(f"unhandled mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
