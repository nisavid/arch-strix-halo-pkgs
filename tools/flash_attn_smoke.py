#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import sys


_VALIDATED_BACKEND_MODULE = (
    "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2"
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded FlashAttention smoke.")
    parser.add_argument(
        "--mode",
        required=True,
        choices=("backend-import", "qkvpacked-tiny"),
        help="which FlashAttention smoke path to run",
    )
    parser.add_argument("--batch-size", type=_positive_int, default=1)
    parser.add_argument("--seqlen", type=_positive_int, default=16)
    parser.add_argument("--heads", type=_positive_int, default=2)
    parser.add_argument("--head-dim", type=_positive_int, default=32)
    parser.add_argument("--seed", type=int)
    return parser


def _import_flash_attn():
    return importlib.import_module("flash_attn")


def _backend_module(flash_attn):
    wrapper = getattr(flash_attn, "flash_attn_interface", None)
    if wrapper is None:
        raise RuntimeError("FLASH_ATTN_BACKEND_NOT_FOUND")

    if getattr(wrapper, "USE_TRITON_ROCM", False) is not True:
        raise RuntimeError("flash_attn.flash_attn_interface USE_TRITON_ROCM != True")

    backend = getattr(wrapper, "flash_attn_gpu", None)
    if backend is None:
        raise RuntimeError("flash_attn.flash_attn_interface.flash_attn_gpu missing")

    backend_name = getattr(backend, "__name__", None)
    if backend_name != _VALIDATED_BACKEND_MODULE:
        raise RuntimeError(
            "flash_attn.flash_attn_interface.flash_attn_gpu "
            f"{backend_name} != {_VALIDATED_BACKEND_MODULE}"
        )

    return wrapper, backend


def _run_backend_import() -> int:
    try:
        flash_attn = _import_flash_attn()
    except (ImportError, ModuleNotFoundError, RuntimeError, AttributeError) as exc:
        print(f"flash_attn_import_error {exc}")
        return 1

    try:
        wrapper, backend = _backend_module(flash_attn)
    except RuntimeError as exc:
        print(f"flash_attn_backend_error {exc}")
        return 1

    use_triton_rocm = bool(getattr(wrapper, "USE_TRITON_ROCM", False))
    print("mode backend-import")
    print(f"flash_attn_version {getattr(flash_attn, '__version__', 'unknown')}")
    print(f"use_triton_rocm {use_triton_rocm}")
    print(f"backend_module {backend.__name__}")
    print(f"backend_file {getattr(backend, '__file__', 'unknown')}")
    if not use_triton_rocm:
        return 1
    print("flash_attn_import_ok")
    return 0


def _load_torch():
    return importlib.import_module("torch")


def _is_finite(torch, tensor) -> bool:
    finite_value = torch.isfinite(tensor).all()
    if hasattr(finite_value, "item"):
        return bool(finite_value.item())
    return bool(finite_value)


def _run_qkvpacked_tiny(args: argparse.Namespace) -> int:
    try:
        torch = _load_torch()
        flash_attn = _import_flash_attn()
    except (ImportError, ModuleNotFoundError, RuntimeError, AttributeError) as exc:
        print(f"flash_attn_import_error {exc}")
        return 1

    if not torch.cuda.is_available():
        print("cuda_available False")
        return 1

    if args.seed is not None:
        torch.manual_seed(args.seed)

    device = torch.device("cuda")
    generator = None
    if args.seed is not None and hasattr(torch, "Generator"):
        generator = torch.Generator(device="cpu").manual_seed(args.seed)

    qkv = torch.randn(
        args.batch_size,
        args.seqlen,
        3,
        args.heads,
        args.head_dim,
        dtype=torch.float16,
        generator=generator,
    ).to(device)

    output = flash_attn.flash_attn_qkvpacked_func(
        qkv,
        dropout_p=0.0,
        causal=False,
    )
    torch.cuda.synchronize()
    expected_shape = (args.batch_size, args.seqlen, args.heads, args.head_dim)
    actual_shape = tuple(output.shape)
    finite = _is_finite(torch, output)

    print("mode qkvpacked-tiny")
    print(f"shape {actual_shape}")
    print(f"finite {finite}")
    if actual_shape != expected_shape or not finite:
        return 1
    print("flash_attn_qkvpacked_ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "backend-import":
        return _run_backend_import()
    if args.mode == "qkvpacked-tiny":
        return _run_qkvpacked_tiny(args)
    raise AssertionError(f"unhandled mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
