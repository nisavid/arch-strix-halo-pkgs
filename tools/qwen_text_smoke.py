from __future__ import annotations

import argparse
from collections import Counter
import importlib
import importlib.metadata as metadata
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a text-only offline Qwen smoke through vLLM."
    )
    parser.add_argument("model", help="local model path or Hugging Face model id")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.75)
    parser.add_argument("--max-model-len", type=int, default=128)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--max-num-batched-tokens", type=int, default=None)
    parser.add_argument(
        "--quantization",
        default=None,
        help="optional vLLM quantization method override, such as quark",
    )
    parser.add_argument(
        "--kv-cache-dtype",
        default=None,
        help="optional vLLM KV cache dtype override, such as fp8",
    )
    parser.add_argument(
        "--dtype",
        default=None,
        help="optional vLLM model dtype override, such as float16",
    )
    parser.add_argument(
        "--execution-mode",
        choices=("eager", "compiled"),
        default="eager",
        help="use eager correctness mode or allow vLLM compilation/cudagraph paths",
    )
    parser.add_argument(
        "--attention-backend",
        default=None,
        help="optional vLLM attention backend override, such as FLASH_ATTN",
    )
    parser.add_argument(
        "--expected-flash-attn-backend",
        choices=("ck", "triton-amd"),
        default=None,
        help="assert the installed flash_attn backend when --attention-backend FLASH_ATTN",
    )
    return parser.parse_args()


def resolved_model_arg(model: str) -> str:
    path = Path(model)
    if path.exists():
        return str(path.resolve())
    return model


def print_config_summary(config: Any) -> None:
    architectures = getattr(config, "architectures", None) or []
    print("config_architectures", ",".join(str(value) for value in architectures))
    print("config_model_type", getattr(config, "model_type", ""))

    text_config = getattr(config, "text_config", None)
    if text_config is not None:
        print("text_config_model_type", getattr(text_config, "model_type", ""))

    for attr in (
        "hidden_size",
        "num_attention_heads",
        "num_hidden_layers",
        "num_experts",
        "num_experts_per_tok",
        "num_key_value_heads",
        "head_dim",
    ):
        value = getattr(config, attr, None)
        if value is None and text_config is not None:
            value = getattr(text_config, attr, None)
        if value is not None:
            print(f"config_{attr}", value)

    layer_types = getattr(config, "layer_types", None)
    if layer_types is None and text_config is not None:
        layer_types = getattr(text_config, "layer_types", None)
    if layer_types:
        counts = Counter(str(value) for value in layer_types)
        summary = ",".join(f"{key}:{counts[key]}" for key in sorted(counts))
        print("config_layer_types", summary)

    quantization_config = getattr(config, "quantization_config", None)
    quantization_config_present = quantization_config is not None
    print("config_quantization_config_present", str(quantization_config_present).lower())
    if quantization_config_present:
        print("config_quantization_config", repr(quantization_config))


def render_prompt(tokenizer: Any) -> str:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a short answer: say the word ready."},
    ]
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except TypeError:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )


def validate_nonempty_text(text: str) -> None:
    stripped = text.strip()
    if not stripped:
        raise AssertionError("empty model output")


def print_flash_attn_backend_summary(expected: str | None = None) -> None:
    flash_attn = importlib.import_module("flash_attn")
    wrapper = getattr(flash_attn, "flash_attn_interface", None)
    if wrapper is None:
        raise AssertionError("flash_attn.flash_attn_interface missing")

    use_triton_rocm = bool(getattr(wrapper, "USE_TRITON_ROCM", False))
    backend = getattr(wrapper, "flash_attn_gpu", None)
    backend_module = getattr(backend, "__name__", "missing")
    backend_file = getattr(backend, "__file__", "unknown")

    print("flash_attn_use_triton_rocm", use_triton_rocm)
    print("flash_attn_backend_module", backend_module)
    print("flash_attn_backend_file", backend_file)

    if expected == "ck":
        if use_triton_rocm or backend_module != "flash_attn_2_cuda":
            raise AssertionError("expected FlashAttention CK backend")
    elif expected == "triton-amd":
        if not use_triton_rocm or not backend_module.startswith(
            "aiter.ops.triton._triton_kernels.flash_attn_triton_amd"
        ):
            raise AssertionError("expected FlashAttention Triton AMD backend")


def build_llm_kwargs(model: str, args: argparse.Namespace) -> dict[str, Any]:
    llm_kwargs: dict[str, Any] = {
        "model": model,
        "trust_remote_code": True,
        "max_model_len": args.max_model_len,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "tensor_parallel_size": 1,
        "limit_mm_per_prompt": {"image": 0, "audio": 0, "video": 0},
        "disable_log_stats": True,
    }
    if args.execution_mode == "eager":
        llm_kwargs["enforce_eager"] = True
    if args.max_num_batched_tokens is not None:
        llm_kwargs["max_num_batched_tokens"] = args.max_num_batched_tokens
    if args.quantization:
        llm_kwargs["quantization"] = args.quantization
    if args.kv_cache_dtype:
        llm_kwargs["kv_cache_dtype"] = args.kv_cache_dtype
    if args.dtype:
        llm_kwargs["dtype"] = args.dtype
    if args.attention_backend:
        llm_kwargs["attention_backend"] = args.attention_backend
    return llm_kwargs


def main() -> None:
    args = parse_args()
    model = resolved_model_arg(args.model)

    import torch
    from transformers import AutoConfig, AutoTokenizer
    from vllm import LLM, SamplingParams

    print("model", model)
    print("vllm", metadata.version("vllm"))
    print("torch", torch.__version__)
    print("cuda_available", torch.cuda.is_available())
    print("cuda_device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("cuda_device_0", torch.cuda.get_device_name(0))
    print("gpu_memory_utilization", args.gpu_memory_utilization)
    print("max_model_len", args.max_model_len)
    print("max_tokens", args.max_tokens)
    print("max_num_batched_tokens", args.max_num_batched_tokens)
    print("quantization", args.quantization)
    print("kv_cache_dtype", args.kv_cache_dtype)
    print("dtype", args.dtype)
    print("attention_backend", args.attention_backend)
    print("expected_flash_attn_backend", args.expected_flash_attn_backend)
    if args.attention_backend == "FLASH_ATTN" or args.expected_flash_attn_backend:
        print_flash_attn_backend_summary(args.expected_flash_attn_backend)

    config = AutoConfig.from_pretrained(model, trust_remote_code=True)
    print_config_summary(config)

    tokenizer = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
    prompt = render_prompt(tokenizer)
    print("rendered_prompt:", repr(prompt))

    llm_kwargs = build_llm_kwargs(model, args)
    llm = LLM(**llm_kwargs)
    print("llm_init_ok")

    outputs = llm.generate(
        [prompt],
        SamplingParams(
            max_tokens=args.max_tokens,
            min_tokens=1,
            temperature=0.0,
            skip_special_tokens=False,
        ),
    )
    print("generation_ok")
    for request in outputs:
        print("request_prompt:", repr(request.prompt))
        print("prompt_token_count:", len(request.prompt_token_ids or []))
        for idx, output in enumerate(request.outputs):
            print(f"output_{idx}_text:", repr(output.text))
            print(f"output_{idx}_token_ids:", list(output.token_ids))
            print(f"output_{idx}_finish_reason:", repr(output.finish_reason))
            print(f"output_{idx}_stop_reason:", repr(output.stop_reason))
            validate_nonempty_text(output.text)
    print("basic_ok")


if __name__ == "__main__":
    main()
