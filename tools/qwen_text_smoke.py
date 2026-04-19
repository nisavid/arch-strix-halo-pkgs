from __future__ import annotations

import argparse
from collections import Counter
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
        "--execution-mode",
        choices=("eager", "compiled"),
        default="eager",
        help="use eager correctness mode or allow vLLM compilation/cudagraph paths",
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
        "num_hidden_layers",
        "num_experts",
        "num_experts_per_tok",
        "num_key_value_heads",
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
    if quantization_config:
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

    config = AutoConfig.from_pretrained(model, trust_remote_code=True)
    print_config_summary(config)

    tokenizer = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
    prompt = render_prompt(tokenizer)
    print("rendered_prompt:", repr(prompt))

    llm_kwargs = {
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
