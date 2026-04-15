from __future__ import annotations

import importlib.metadata as metadata
import sys
from pathlib import Path

import torch
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: gemma4_text_smoke.py /path/to/model")

    model = Path(sys.argv[1]).resolve()

    print("model", str(model))
    print("vllm", metadata.version("vllm"))
    print("torch", torch.__version__)
    print("cuda_available", torch.cuda.is_available())
    print("cuda_device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("cuda_device_0", torch.cuda.get_device_name(0))

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

    llm = LLM(
        model=str(model),
        trust_remote_code=True,
        max_model_len=128,
        gpu_memory_utilization=0.75,
        tensor_parallel_size=1,
        enforce_eager=True,
        limit_mm_per_prompt={"image": 0, "audio": 0, "video": 0},
        disable_log_stats=True,
    )
    print("llm_init_ok")

    outputs = llm.generate(
        [prompt],
        SamplingParams(
            max_tokens=16,
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


if __name__ == "__main__":
    main()
