#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import sys


_VALIDATED_TRITON_BACKEND_MODULE = (
    "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2"
)
_VALIDATED_CK_BACKEND_MODULE = "flash_attn_2_cuda"


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
        choices=(
            "backend-import",
            "qkvpacked-tiny",
            "ck-backend-import",
            "ck-qkvpacked-tiny",
        ),
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


def _backend_module(flash_attn, *, backend: str):
    wrapper = getattr(flash_attn, "flash_attn_interface", None)
    if wrapper is None:
        raise RuntimeError("FLASH_ATTN_BACKEND_NOT_FOUND")

    use_triton_rocm = getattr(wrapper, "USE_TRITON_ROCM", False)
    if backend == "triton-amd" and use_triton_rocm is not True:
        raise RuntimeError("flash_attn.flash_attn_interface USE_TRITON_ROCM != True")
    if backend == "ck" and use_triton_rocm is not False:
        raise RuntimeError("flash_attn.flash_attn_interface USE_TRITON_ROCM != False")

    backend = getattr(wrapper, "flash_attn_gpu", None)
    if backend is None:
        raise RuntimeError("flash_attn.flash_attn_interface.flash_attn_gpu missing")

    backend_name = getattr(backend, "__name__", None)
    expected_backend = (
        _VALIDATED_TRITON_BACKEND_MODULE
        if use_triton_rocm
        else _VALIDATED_CK_BACKEND_MODULE
    )
    if backend_name != expected_backend:
        raise RuntimeError(
            "flash_attn.flash_attn_interface.flash_attn_gpu "
            f"{backend_name} != {expected_backend}"
        )

    return wrapper, backend


def _run_backend_import(*, backend: str, mode: str, ok_marker: str) -> int:
    try:
        flash_attn = _import_flash_attn()
    except (ImportError, ModuleNotFoundError, RuntimeError, AttributeError) as exc:
        print(f"flash_attn_import_error {exc}")
        return 1

    try:
        wrapper, backend_module = _backend_module(flash_attn, backend=backend)
    except RuntimeError as exc:
        print(f"flash_attn_backend_error {exc}")
        return 1

    use_triton_rocm = bool(getattr(wrapper, "USE_TRITON_ROCM", False))
    print(f"mode {mode}")
    print(f"flash_attn_version {getattr(flash_attn, '__version__', 'unknown')}")
    print(f"use_triton_rocm {use_triton_rocm}")
    print(f"backend_module {backend_module.__name__}")
    print(f"backend_file {getattr(backend_module, '__file__', 'unknown')}")
    print(ok_marker)
    return 0


def _load_torch():
    return importlib.import_module("torch")


def _is_finite(torch, tensor) -> bool:
    finite_value = torch.isfinite(tensor).all()
    if hasattr(finite_value, "item"):
        return bool(finite_value.item())
    return bool(finite_value)


def _run_qkvpacked_tiny(
    args: argparse.Namespace,
    *,
    backend: str | None = None,
    mode: str = "qkvpacked-tiny",
    ok_marker: str = "flash_attn_qkvpacked_ok",
) -> int:
    try:
        torch = _load_torch()
        flash_attn = _import_flash_attn()
    except (ImportError, ModuleNotFoundError, RuntimeError, AttributeError) as exc:
        print(f"flash_attn_import_error {exc}")
        return 1

    if not torch.cuda.is_available():
        print("cuda_available False")
        return 1

    if backend is not None:
        try:
            _backend_module(flash_attn, backend=backend)
        except RuntimeError as exc:
            print(f"flash_attn_backend_error {exc}")
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

    print(f"mode {mode}")
    print(f"shape {actual_shape}")
    print(f"finite {finite}")
    if actual_shape != expected_shape or not finite:
        return 1
    print(ok_marker)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "backend-import":
        return _run_backend_import(
            backend="triton-amd",
            mode="backend-import",
            ok_marker="flash_attn_import_ok",
        )
    if args.mode == "qkvpacked-tiny":
        return _run_qkvpacked_tiny(args)
    if args.mode == "ck-backend-import":
        return _run_backend_import(
            backend="ck",
            mode="ck-backend-import",
            ok_marker="flash_attn_ck_import_ok",
        )
    if args.mode == "ck-qkvpacked-tiny":
        return _run_qkvpacked_tiny(
            args,
            backend="ck",
            mode="ck-qkvpacked-tiny",
            ok_marker="flash_attn_ck_qkvpacked_ok",
        )
    raise AssertionError(f"unhandled mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
