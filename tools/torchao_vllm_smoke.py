from __future__ import annotations

import argparse
from collections import OrderedDict
import json
import shutil
import sys
from importlib import metadata
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file
from torchao.core.config import config_to_dict
from torchao.prototype.safetensors.safetensors_support import (
    flatten_tensor_state_dict,
    unflatten_tensor_state_dict,
)
from torchao.quantization import FqnToConfig, Int8WeightOnlyConfig, quantize_
from transformers import (
    AutoModelForCausalLM,
    AutoProcessor,
    AutoTokenizer,
    LlamaConfig,
    LlamaForCausalLM,
    TorchAoConfig,
)

TORCHAO_VERSION_WARNING = "Stored version is not the same as current default version"
ROCM_PAGED_ATTENTION_WARNING = (
    "Cannot use ROCm custom paged attention kernel, falling back to Triton implementation"
)
WARNING_MARKERS = [TORCHAO_VERSION_WARNING, ROCM_PAGED_ATTENTION_WARNING]
REAL_MODEL_SKIP_MODULES = [
    "model.vision_tower",
    "model.audio_tower",
    "model.embed_vision",
    "model.embed_audio",
    "vision_tower",
    "audio_tower",
    "embed_vision",
    "embed_audio",
]
REAL_MODEL_LANGUAGE_QUANT_PATTERNS = [
    r"re:(model\.)?language_model\..*",
    r"re:lm_head\..*",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a tiny TorchAO-serialized model and optionally run a vLLM load/generate smoke."
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("/tmp/torchao-vllm-smoke"),
        help="scratch directory used for the tiny base and quantized checkpoints",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="only build the tiny TorchAO checkpoint; skip the vLLM load/generate phase",
    )
    parser.add_argument(
        "--source-model",
        help="dense model ID or local path to quantize with TorchAO int8 weight-only before serving",
    )
    parser.add_argument(
        "--quantized-model",
        type=Path,
        help="existing TorchAO-serialized model path to serve directly",
    )
    parser.add_argument("--max-model-len", type=int, default=128)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.5)
    parser.add_argument(
        "--online-quantization",
        action="store_true",
        help="serve --source-model directly and let vLLM apply TorchAO after loading high-precision weights",
    )
    parser.add_argument(
        "--execution-mode",
        choices=("eager", "compiled"),
        default="eager",
        help="use eager correctness mode or allow vLLM compilation/cudagraph paths",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.online_quantization and args.source_model is None:
        parser.error("--online-quantization requires --source-model")
    if args.online_quantization and args.quantized_model is not None:
        parser.error("--online-quantization cannot be combined with --quantized-model")
    return args


def real_quant_dir(work_dir: Path) -> Path:
    return work_dir / "real-model-torchao"


def display_model_ref(model_ref: str) -> str:
    path = Path(model_ref)
    if path.exists() or model_ref.startswith(("/", ".")):
        return str(path.resolve())
    return model_ref


def build_plan(args: argparse.Namespace) -> dict[str, object]:
    work_dir = args.work_dir.resolve()
    quantized_model = (
        args.quantized_model.resolve()
        if args.quantized_model is not None
        else real_quant_dir(work_dir)
    )
    mode = "real-model" if args.source_model is not None or args.quantized_model is not None else "tiny"
    if args.source_model is not None and args.online_quantization:
        mode = "real-model-online"
    quantized_model_ref = {
        "real-model": str(quantized_model),
        "real-model-online": None,
        "tiny": str(work_dir / "tiny-llama-torchao"),
    }[mode]
    return {
        "mode": mode,
        "work_dir": str(work_dir),
        "source_model": display_model_ref(args.source_model) if args.source_model else None,
        "quantized_model": quantized_model_ref,
        "prepare_only": args.prepare_only,
        "quantization": "torchao-int8-weight-only",
        "max_model_len": args.max_model_len,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "online_quantization": args.online_quantization,
        "execution_mode": args.execution_mode,
        "serialized_skip_modules": REAL_MODEL_SKIP_MODULES
        if mode == "real-model"
        else [],
        "serialized_quant_patterns": REAL_MODEL_LANGUAGE_QUANT_PATTERNS
        if mode == "real-model"
        else [],
        "warning_markers": WARNING_MARKERS,
    }


def classify_warning_text(text: str) -> dict[str, bool]:
    return {
        "torchao_version_mismatch": TORCHAO_VERSION_WARNING in text,
        "rocm_paged_attention_fallback": ROCM_PAGED_ATTENTION_WARNING in text,
    }


def prepare_checkpoint(work_dir: Path) -> Path:
    base_dir = work_dir / "tiny-llama-base"
    quant_dir = work_dir / "tiny-llama-torchao"

    for path in (base_dir, quant_dir):
        if path.exists():
            shutil.rmtree(path)

    config = LlamaConfig(
        vocab_size=256,
        hidden_size=128,
        intermediate_size=256,
        num_hidden_layers=2,
        num_attention_heads=2,
        num_key_value_heads=2,
        max_position_embeddings=64,
        bos_token_id=1,
        eos_token_id=2,
        tie_word_embeddings=False,
    )
    torch.manual_seed(0)
    LlamaForCausalLM(config).save_pretrained(base_dir, safe_serialization=False)

    quantization_config = TorchAoConfig(
        Int8WeightOnlyConfig(version=2),
        untie_embedding_weights=True,
    )
    quantized_model = AutoModelForCausalLM.from_pretrained(
        base_dir,
        quantization_config=quantization_config,
        dtype=torch.bfloat16,
        device_map="cpu",
    )
    quantized_model.save_pretrained(quant_dir, safe_serialization=True)

    quantized_config = json.loads((quant_dir / "config.json").read_text())
    print("prepare_ok")
    print("quant_dir", str(quant_dir))
    print("quant_method", quantized_config["quantization_config"]["quant_method"])
    print(
        "quant_type_keys",
        sorted(quantized_config["quantization_config"]["quant_type"].keys()),
    )
    print("checkpoint_files", sorted(path.name for path in quant_dir.iterdir()))

    return quant_dir


def save_processor_or_tokenizer(source_model: str, quant_dir: Path) -> None:
    try:
        processor = AutoProcessor.from_pretrained(source_model, trust_remote_code=True)
    except (OSError, ValueError):
        tokenizer = AutoTokenizer.from_pretrained(source_model, trust_remote_code=True)
        tokenizer.save_pretrained(quant_dir)
    else:
        processor.save_pretrained(quant_dir)


def prepare_real_checkpoint(source_model: str, quant_dir: Path) -> Path:
    if quant_dir.exists():
        shutil.rmtree(quant_dir)
    quant_dir.parent.mkdir(parents=True, exist_ok=True)

    int8_config = Int8WeightOnlyConfig(version=2)
    quantization_config = TorchAoConfig(
        FqnToConfig(
            OrderedDict(
                (pattern, int8_config)
                for pattern in REAL_MODEL_LANGUAGE_QUANT_PATTERNS
            )
        ),
        modules_to_not_convert=REAL_MODEL_SKIP_MODULES,
        untie_embedding_weights=True,
    )
    quantized_model = AutoModelForCausalLM.from_pretrained(
        source_model,
        dtype=torch.bfloat16,
        device_map="cpu",
        trust_remote_code=True,
    )
    quantize_(quantized_model.model.language_model, int8_config)
    quantized_model.config.quantization_config = quantization_config
    quantized_model.config.save_pretrained(quant_dir)
    if getattr(quantized_model, "generation_config", None) is not None:
        quantized_model.generation_config.save_pretrained(quant_dir)
    tensors, tensor_metadata = flatten_tensor_state_dict(quantized_model.state_dict())
    cloned_tensors = {
        name: tensor.detach().cpu().contiguous().clone()
        for name, tensor in tensors.items()
    }
    save_file(cloned_tensors, quant_dir / "model.safetensors", metadata=tensor_metadata)
    save_processor_or_tokenizer(source_model, quant_dir)

    print("prepare_real_ok")
    print("source_model", display_model_ref(source_model))
    print("quant_dir", str(quant_dir))
    print("skip_quantized_modules", json.dumps(REAL_MODEL_SKIP_MODULES, sort_keys=True))
    print(
        "quantized_patterns",
        json.dumps(REAL_MODEL_LANGUAGE_QUANT_PATTERNS, sort_keys=True),
    )
    return quant_dir


def tensor_summary(tensor: torch.Tensor) -> dict[str, object]:
    summary: dict[str, object] = {
        "type": type(tensor).__name__,
        "shape": list(tensor.shape),
    }
    for attr_name in (
        "tensor_data_names",
        "tensor_attribute_names",
        "optional_tensor_data_names",
        "optional_tensor_attribute_names",
        "block_size",
        "dtype",
        "act_quant_kwargs",
    ):
        if hasattr(tensor, attr_name):
            value = getattr(tensor, attr_name)
            if isinstance(value, torch.dtype):
                summary[attr_name] = str(value)
            else:
                summary[attr_name] = repr(value)

    tensor_data = {}
    for data_name in getattr(tensor, "tensor_data_names", []):
        value = getattr(tensor, data_name)
        tensor_data[data_name] = {
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "device": str(value.device),
        }
    for data_name in getattr(tensor, "optional_tensor_data_names", []):
        value = getattr(tensor, data_name)
        if value is None:
            tensor_data[data_name] = None
        else:
            tensor_data[data_name] = {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "device": str(value.device),
            }
    if tensor_data:
        summary["tensor_data"] = tensor_data

    return summary


def build_quantized_destination(
    shape: tuple[int, int], *, device: str
) -> torch.nn.Parameter:
    from torchao.quantization import quantize_

    param = torch.nn.Parameter(
        torch.empty(shape, device=device, dtype=torch.bfloat16),
        requires_grad=False,
    )
    with torch.device("meta"):
        dummy_linear = torch.nn.Sequential(
            torch.nn.Linear(shape[1], shape[0], bias=False)
        )
    dummy_linear[0].weight = param
    quantize_(dummy_linear, Int8WeightOnlyConfig(version=2))
    return dummy_linear[0].weight


def load_serialized_weight(model_dir: Path, weight_name: str) -> torch.Tensor:
    with safe_open(str(model_dir / "model.safetensors"), framework="pt", device="cpu") as f:
        metadata = f.metadata()
        tensors = {name: f.get_tensor(name) for name in f.keys()}
    reconstructed, leftover = unflatten_tensor_state_dict(tensors, metadata)
    if leftover:
        raise RuntimeError(f"unexpected leftover tensors: {sorted(leftover)[:8]}")
    return reconstructed[weight_name]


def copy_with_debug(dst: torch.Tensor, src: torch.Tensor, label: str) -> None:
    try:
        dst.copy_(src)
    except Exception:
        print(f"{label}_copy_fail")
        print(
            f"{label}_dst",
            json.dumps(tensor_summary(dst), sort_keys=True),
        )
        print(
            f"{label}_src",
            json.dumps(tensor_summary(src), sort_keys=True),
        )
        raise
    print(f"{label}_copy_ok")


def run_copy_probe(model_dir: Path) -> None:
    if not torch.cuda.is_available():
        print("copy_probe_skipped_no_cuda")
        return

    device = "cuda"
    q_proj = load_serialized_weight(
        model_dir, "model.layers.0.self_attn.q_proj.weight"
    ).to(device)
    gate_proj = load_serialized_weight(
        model_dir, "model.layers.0.mlp.gate_proj.weight"
    ).to(device)

    standalone = build_quantized_destination(tuple(q_proj.shape), device=device)
    copy_with_debug(standalone, q_proj, "copy_probe_standalone_q_proj")

    qkv = build_quantized_destination((q_proj.shape[0] * 3, q_proj.shape[1]), device=device)
    for shard, start in (("q", 0), ("k", q_proj.shape[0]), ("v", q_proj.shape[0] * 2)):
        copy_with_debug(
            qkv.narrow(0, start, q_proj.shape[0]),
            q_proj,
            f"copy_probe_qkv_{shard}",
        )

    gate_up = build_quantized_destination(
        (gate_proj.shape[0] * 2, gate_proj.shape[1]),
        device=device,
    )
    for shard, start in ((0, 0), (1, gate_proj.shape[0])):
        copy_with_debug(
            gate_up.narrow(0, start, gate_proj.shape[0]),
            gate_proj,
            f"copy_probe_gate_up_{shard}",
        )

    print("copy_probe_ok")


def run_vllm_smoke(
    model_dir: Path,
    *,
    max_model_len: int = 64,
    gpu_memory_utilization: float = 0.2,
    execution_mode: str = "eager",
    skip_tokenizer_init: bool = True,
    online_torchao: bool = False,
) -> None:
    from vllm import LLM, SamplingParams

    print("model", str(model_dir))
    print("vllm", metadata.version("vllm"))
    print("torch", torch.__version__)
    print("cuda_available", torch.cuda.is_available())
    print("cuda_device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("cuda_device_0", torch.cuda.get_device_name(0))

    llm_kwargs = {
        "model": str(model_dir),
        "skip_tokenizer_init": skip_tokenizer_init,
        "max_model_len": max_model_len,
        "gpu_memory_utilization": gpu_memory_utilization,
        "tensor_parallel_size": 1,
        "disable_log_stats": True,
    }
    if online_torchao:
        llm_kwargs["quantization"] = "torchao"
        llm_kwargs["hf_overrides"] = {
            "quantization_config_dict_json": json.dumps(
                config_to_dict(Int8WeightOnlyConfig(version=2))
            )
        }
    if execution_mode == "eager":
        llm_kwargs["enforce_eager"] = True
    llm = LLM(**llm_kwargs)
    print("llm_init_ok")

    sampling_params = SamplingParams(max_tokens=8, min_tokens=1, temperature=0.0)
    if skip_tokenizer_init:
        prompt_token_ids = [1, 5, 7, 9]
        outputs = llm.generate(
            [{"prompt_token_ids": prompt_token_ids}],
            sampling_params,
            use_tqdm=False,
        )
    else:
        outputs = llm.generate(["Write exactly five words."], sampling_params, use_tqdm=False)
    print("generation_ok")
    for request in outputs:
        if request.prompt_token_ids is not None:
            print("request_prompt_token_ids", list(request.prompt_token_ids or []))
        for idx, output in enumerate(request.outputs):
            print(f"output_{idx}_text", repr(output.text))
            print(f"output_{idx}_token_ids", list(output.token_ids))
            print(f"output_{idx}_finish_reason", repr(output.finish_reason))
            print(f"output_{idx}_stop_reason", repr(output.stop_reason))


def main() -> None:
    args = parse_args()
    plan = build_plan(args)
    if args.dry_run:
        json.dump(plan, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return

    work_dir = args.work_dir.resolve()
    if args.source_model is not None and args.online_quantization:
        quant_dir = Path(args.source_model)
        print("using_online_source_model", display_model_ref(args.source_model))
    elif args.source_model is not None:
        quant_dir = prepare_real_checkpoint(args.source_model, real_quant_dir(work_dir))
    elif args.quantized_model is not None:
        quant_dir = args.quantized_model.resolve()
        print("using_quantized_model", str(quant_dir))
    else:
        quant_dir = prepare_checkpoint(work_dir)

    if not args.prepare_only:
        if args.source_model is None and args.quantized_model is None:
            run_copy_probe(quant_dir)
            run_vllm_smoke(quant_dir)
        else:
            run_vllm_smoke(
                quant_dir,
                max_model_len=args.max_model_len,
                gpu_memory_utilization=args.gpu_memory_utilization,
                execution_mode=args.execution_mode,
                skip_tokenizer_init=False,
                online_torchao=args.online_quantization,
            )
        print("warning_markers", json.dumps(WARNING_MARKERS, sort_keys=True))


if __name__ == "__main__":
    main()
