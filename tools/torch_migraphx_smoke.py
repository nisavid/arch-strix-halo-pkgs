#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import sys
import time
from typing import Callable


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _load_torch_stack():
    import torch
    import torch_migraphx.dynamo  # noqa: F401 - registers the migraphx backend

    return torch


def _device(torch):
    if not torch.cuda.is_available():
        raise RuntimeError("TORCH_MIGRAPHX_CUDA_UNAVAILABLE")
    return torch.device("cuda")


def _sync(torch) -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def _peak_memory_bytes(torch) -> int | None:
    try:
        return int(torch.cuda.max_memory_allocated())
    except Exception:
        return None


def _reset_peak_memory(torch) -> None:
    try:
        torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass


def _mean_latency_ms(torch, fn: Callable[[], object], iterations: int) -> float:
    samples: list[float] = []
    for _ in range(iterations):
        _sync(torch)
        started = time.perf_counter()
        fn()
        _sync(torch)
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.fmean(samples)


def _build_tiny_resnet(torch):
    nn = torch.nn

    class ResidualBlock(nn.Module):
        def __init__(self, channels: int) -> None:
            super().__init__()
            self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
            self.bn1 = nn.BatchNorm2d(channels)
            self.relu = nn.ReLU()
            self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
            self.bn2 = nn.BatchNorm2d(channels)

        def forward(self, x):
            residual = x
            x = self.relu(self.bn1(self.conv1(x)))
            x = self.bn2(self.conv2(x))
            return self.relu(x + residual)

    class TinyResNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.stem = nn.Sequential(
                nn.Conv2d(3, 8, kernel_size=3, padding=1),
                nn.BatchNorm2d(8),
                nn.ReLU(),
            )
            self.block = ResidualBlock(8)
            self.pool = nn.AdaptiveAvgPool2d((1, 1))
            self.fc = nn.Linear(8, 4)

        def forward(self, x):
            x = self.stem(x)
            x = self.block(x)
            x = self.pool(x)
            x = torch.flatten(x, 1)
            return self.fc(x)

    return TinyResNet()


def _make_input(torch, args: argparse.Namespace, device):
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    sample = torch.randn(
        args.batch_size,
        3,
        args.height,
        args.width,
        generator=generator,
        dtype=torch.float32,
    )
    return sample.to(device)


def _run_pt2e_quantizer_import() -> int:
    from torchao.quantization.pt2e.quantize_pt2e import convert_pt2e, prepare_pt2e
    from torch_migraphx.dynamo.quantization.migraphx_quantizer import MGXQuantizer

    quantizer = MGXQuantizer()
    print("mode pt2e-quantizer-import")
    quantizer_class = f"{quantizer.__class__.__module__}.{quantizer.__class__.__name__}"
    print(f"quantizer_class {quantizer_class}")
    print(f"prepare_pt2e {prepare_pt2e.__module__}.{prepare_pt2e.__name__}")
    print(f"convert_pt2e {convert_pt2e.__module__}.{convert_pt2e.__name__}")
    print("pt2e_quantizer_import_ok")
    return 0


def _prepare_pt2e_model(torch, model, sample, calibration_batches: int):
    from torchao.quantization.pt2e.quantize_pt2e import convert_pt2e, prepare_pt2e
    from torch_migraphx.dynamo.quantization.migraphx_quantizer import MGXQuantizer

    exported = torch.export.export(model, (sample,), strict=True).module()
    prepared = prepare_pt2e(exported, MGXQuantizer())
    with torch.inference_mode():
        for index in range(calibration_batches):
            prepared(sample + (index * 0.001))
    return convert_pt2e(prepared, fold_quantize=False)


def _run_resnet(args: argparse.Namespace, *, quantize_pt2e: bool) -> int:
    torch = _load_torch_stack()
    device = _device(torch)
    torch.manual_seed(args.seed)
    model = _build_tiny_resnet(torch).eval().to(device)
    sample = _make_input(torch, args, device)

    if quantize_pt2e:
        model = _prepare_pt2e_model(torch, model, sample, args.calibration_batches)

    _reset_peak_memory(torch)
    with torch.inference_mode():
        expected = model(sample)
        baseline_latency = _mean_latency_ms(
            torch, lambda: model(sample), iterations=args.iterations
        )

        compiled = torch.compile(model, backend="migraphx")
        for _ in range(args.warmup):
            compiled(sample)
        _sync(torch)

        actual = compiled(sample)
        torch.testing.assert_close(
            actual,
            expected,
            rtol=args.rtol,
            atol=args.atol,
            check_dtype=True,
        )
        compiled_latency = _mean_latency_ms(
            torch, lambda: compiled(sample), iterations=args.iterations
        )

    max_abs_diff = float((actual - expected).abs().max().detach().cpu())
    peak_memory = _peak_memory_bytes(torch)
    mode = "pt2e-resnet-tiny" if quantize_pt2e else "dynamo-resnet-tiny"
    print(f"mode {mode}")
    print(f"device {torch.cuda.get_device_name(device)}")
    print(f"input_shape {tuple(sample.shape)}")
    print(f"baseline_latency_ms {baseline_latency:.4f}")
    print(f"compiled_latency_ms {compiled_latency:.4f}")
    print(f"speedup {baseline_latency / compiled_latency:.4f}")
    print(f"max_abs_diff {max_abs_diff:.8f}")
    print(
        "peak_memory_bytes "
        + (str(peak_memory) if peak_memory is not None else "unavailable")
    )
    print("output_close_ok")
    print("torch_migraphx_ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded Torch-MIGraphX import and Dynamo smoke probes."
    )
    parser.add_argument(
        "--mode",
        choices=[
            "pt2e-quantizer-import",
            "dynamo-resnet-tiny",
            "pt2e-resnet-tiny",
        ],
        default="dynamo-resnet-tiny",
    )
    parser.add_argument("--batch-size", type=_positive_int, default=1)
    parser.add_argument("--height", type=_positive_int, default=32)
    parser.add_argument("--width", type=_positive_int, default=32)
    parser.add_argument("--warmup", type=_positive_int, default=2)
    parser.add_argument("--iterations", type=_positive_int, default=5)
    parser.add_argument("--calibration-batches", type=_positive_int, default=2)
    parser.add_argument("--seed", type=int, default=20260422)
    parser.add_argument("--rtol", type=float, default=1e-3)
    parser.add_argument("--atol", type=float, default=1e-3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "pt2e-quantizer-import":
        return _run_pt2e_quantizer_import()
    if args.mode == "dynamo-resnet-tiny":
        return _run_resnet(args, quantize_pt2e=False)
    if args.mode == "pt2e-resnet-tiny":
        return _run_resnet(args, quantize_pt2e=True)
    raise AssertionError(f"unhandled mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
