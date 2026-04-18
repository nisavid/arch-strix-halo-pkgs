from __future__ import annotations

import argparse
import importlib.metadata as metadata
import sys
from pathlib import Path

import torch
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from gemma4_smoke_common import validate_basic_chat_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a text-only offline Gemma 4 instruction-tuned smoke through "
            "vLLM using the checkpoint tokenizer chat template."
        )
    )
    parser.add_argument("model", help="local model path or Hugging Face model id")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.75)
    parser.add_argument("--max-model-len", type=int, default=128)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--max-num-batched-tokens", type=int, default=None)
    return parser.parse_args()


def is_gemma4_26b_a4b(model: str) -> bool:
    return "gemma-4-26B-A4B-it" in model


def effective_max_num_batched_tokens(args: argparse.Namespace, model: Path) -> int | None:
    if args.max_num_batched_tokens is not None:
        return args.max_num_batched_tokens
    if is_gemma4_26b_a4b(str(model)):
        return 32
    return None


def main() -> None:
    args = parse_args()
    model = Path(args.model).resolve()
    max_num_batched_tokens = effective_max_num_batched_tokens(args, model)

    print("model", str(model))
    print("vllm", metadata.version("vllm"))
    print("torch", torch.__version__)
    print("cuda_available", torch.cuda.is_available())
    print("cuda_device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("cuda_device_0", torch.cuda.get_device_name(0))
    print("gpu_memory_utilization", args.gpu_memory_utilization)
    print("max_model_len", args.max_model_len)
    print("max_tokens", args.max_tokens)
    print("max_num_batched_tokens", max_num_batched_tokens)

    tokenizer = AutoTokenizer.from_pretrained(str(model), trust_remote_code=True)
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write exactly five words."},
    ]
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    print("rendered_prompt:", repr(prompt))

    llm_kwargs = {
        "model": str(model),
        "trust_remote_code": True,
        "max_model_len": args.max_model_len,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "tensor_parallel_size": 1,
        # Keep the tracked smoke on the validated eager correctness lane until
        # the compiled/cudagraph ROCm path is revalidated separately.
        "enforce_eager": True,
        "limit_mm_per_prompt": {"image": 0, "audio": 0, "video": 0},
        "disable_log_stats": True,
    }
    if max_num_batched_tokens is not None:
        llm_kwargs["max_num_batched_tokens"] = max_num_batched_tokens

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
            validate_basic_chat_text(output.text)
    print("basic_ok")


if __name__ == "__main__":
    main()
