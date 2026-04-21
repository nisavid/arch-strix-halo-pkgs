#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable


EMBEDDING_QUERY = "What is backpropagation?"
EMBEDDING_DOCUMENTS = [
    "Backpropagation is an algorithm for training neural networks by computing gradients.",
    "Paris is the capital city of France.",
]

RERANK_QUERY = "What is 2+2?"
RERANK_DOCUMENTS = [
    "4",
    "Two plus two equals four.",
    "The answer is definitely 1 million.",
]

ZEMBED_QUERY_PREFIX = "<|im_start|>system\nquery<|im_end|>\n<|im_start|>user\n"
ZEMBED_DOCUMENT_PREFIX = "<|im_start|>system\ndocument<|im_end|>\n<|im_start|>user\n"
ZEMBED_SUFFIX = "<|im_end|>\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ZeroEntropy embedding or rerank smokes."
    )
    parser.add_argument("model", help="local model path or Hugging Face model id")
    parser.add_argument(
        "--mode",
        choices=("embeddings", "rerank"),
        required=True,
        help="ZeroEntropy task fixture to run",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="torch device to use; auto selects cuda when available",
    )
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="allow Hugging Face downloads instead of requiring local cache hits",
    )
    return parser.parse_args()


def resolved_model_arg(model: str) -> str:
    path = Path(model)
    if path.exists():
        return str(path.resolve())
    return model


def format_zembed_inputs(query: str, documents: list[str]) -> list[str]:
    return [
        f"{ZEMBED_QUERY_PREFIX}{query}{ZEMBED_SUFFIX}",
        *[
            f"{ZEMBED_DOCUMENT_PREFIX}{document}{ZEMBED_SUFFIX}"
            for document in documents
        ],
    ]


def _assert_finite_values(values: Iterable[float], *, label: str) -> None:
    for index, value in enumerate(values):
        if not math.isfinite(value):
            raise AssertionError(f"{label}_{index}_not_finite: {value!r}")


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise AssertionError("zero-norm embedding vector")
    return numerator / (left_norm * right_norm)


def validate_embedding_fixture(vectors: list[list[float]]) -> None:
    if len(vectors) != 3:
        raise AssertionError(f"embedding_count expected 3, got {len(vectors)}")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise AssertionError(f"embedding dimensions differ: {sorted(dimensions)}")
    dimension = dimensions.pop()
    if dimension <= 0:
        raise AssertionError("embedding dimension must be positive")

    for index, vector in enumerate(vectors):
        _assert_finite_values(vector, label=f"embedding_{index}")

    related = _cosine_similarity(vectors[0], vectors[1])
    unrelated = _cosine_similarity(vectors[0], vectors[2])
    if related <= unrelated:
        raise AssertionError(
            "embedding ranking expected related passage above unrelated passage: "
            f"{related:.6f} <= {unrelated:.6f}"
        )

    print("embedding_count", len(vectors))
    print("embedding_dim", dimension)
    print("embeddings_finite_ok")
    print("embedding_similarity_related", f"{related:.6f}")
    print("embedding_similarity_unrelated", f"{unrelated:.6f}")
    print("embedding_ranking_ok")


def validate_rerank_fixture(scores: list[float]) -> None:
    if len(scores) != 3:
        raise AssertionError(f"score_count expected 3, got {len(scores)}")
    _assert_finite_values(scores, label="score")

    ordered_indices = sorted(
        range(len(scores)),
        key=lambda index: scores[index],
        reverse=True,
    )
    if ordered_indices != [0, 1, 2]:
        raise AssertionError(
            "rerank fixture expected Paris, Berlin, unrelated ordering: "
            f"{ordered_indices!r}"
        )

    print("score_count", len(scores))
    print("scores_finite_ok")
    print("rerank_order", ",".join(str(index) for index in ordered_indices))
    print("rerank_order_ok")


def _torch_device(device_arg: str):
    import torch

    if device_arg != "auto":
        return torch.device(device_arg)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _model_kwargs(*, device, local_files_only: bool):
    import torch

    kwargs = {
        "local_files_only": local_files_only,
        "dtype": torch.bfloat16 if device.type == "cuda" else torch.float32,
        "attn_implementation": "eager",
    }
    if device.type == "cuda":
        kwargs["device_map"] = {"": device}
    return kwargs


def _load_tokenizer(model: str, *, local_files_only: bool):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model,
        padding_side="right",
        local_files_only=local_files_only,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def _load_base_model(model: str, *, device, local_files_only: bool):
    from transformers import AutoModel

    tokenizer = _load_tokenizer(model, local_files_only=local_files_only)
    loaded = AutoModel.from_pretrained(
        model,
        **_model_kwargs(device=device, local_files_only=local_files_only),
    )
    if device.type != "cuda":
        loaded = loaded.to(device)
    loaded.eval()
    return tokenizer, loaded


def _load_causal_lm(model: str, *, device, local_files_only: bool):
    from transformers import AutoModelForCausalLM

    tokenizer = _load_tokenizer(model, local_files_only=local_files_only)
    loaded = AutoModelForCausalLM.from_pretrained(
        model,
        **_model_kwargs(device=device, local_files_only=local_files_only),
    )
    if device.type != "cuda":
        loaded = loaded.to(device)
    loaded.eval()
    return tokenizer, loaded


def _last_token_vectors(hidden_states, attention_mask):
    import torch
    import torch.nn.functional as F

    last_positions = attention_mask.sum(dim=1) - 1
    batch_indices = torch.arange(hidden_states.shape[0], device=hidden_states.device)
    vectors = hidden_states[batch_indices, last_positions]
    vectors = F.normalize(vectors.float(), p=2, dim=1)
    return vectors.detach().cpu().tolist()


def run_embeddings(args: argparse.Namespace, model: str) -> None:
    import torch

    device = _torch_device(args.device)
    tokenizer, loaded = _load_base_model(
        model,
        device=device,
        local_files_only=not args.allow_download,
    )
    prompts = format_zembed_inputs(EMBEDDING_QUERY, EMBEDDING_DOCUMENTS)
    inputs = tokenizer(
        prompts,
        padding=True,
        truncation=True,
        max_length=args.max_length,
        return_tensors="pt",
    ).to(device)
    with torch.inference_mode():
        outputs = loaded(**inputs, output_hidden_states=True, use_cache=False)
    vectors = _last_token_vectors(outputs.hidden_states[-1], inputs.attention_mask)
    validate_embedding_fixture(vectors)
    print("embeddings_ok")


def _format_rerank_inputs(tokenizer, query: str, documents: list[str]) -> list[str]:
    prompts: list[str] = []
    for document in documents:
        messages = [
            {"role": "system", "content": query},
            {"role": "user", "content": document},
        ]
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        if not isinstance(prompt, str):
            raise TypeError(f"chat template returned {type(prompt)!r}")
        prompts.append(prompt)
    return prompts


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def run_rerank(args: argparse.Namespace, model: str) -> None:
    import torch

    device = _torch_device(args.device)
    tokenizer, loaded = _load_causal_lm(
        model,
        device=device,
        local_files_only=not args.allow_download,
    )
    yes_token_id = tokenizer.encode("Yes", add_special_tokens=False)[0]
    prompts = _format_rerank_inputs(tokenizer, RERANK_QUERY, RERANK_DOCUMENTS)
    inputs = tokenizer(
        prompts,
        padding=True,
        truncation=True,
        max_length=args.max_length,
        return_tensors="pt",
    ).to(device)
    with torch.inference_mode():
        outputs = loaded(**inputs, use_cache=False)
    attention_mask = inputs.attention_mask
    last_positions = attention_mask.sum(dim=1) - 1
    batch_indices = torch.arange(outputs.logits.shape[0], device=device)
    last_logits = outputs.logits[batch_indices, last_positions]
    yes_logits = last_logits[:, yes_token_id].float().detach().cpu().tolist()
    scores = [_sigmoid(float(logit) / 5.0) for logit in yes_logits]
    validate_rerank_fixture(scores)
    print("rerank_ok")


def main() -> None:
    args = parse_args()
    model = resolved_model_arg(args.model)

    import torch
    import transformers

    device = _torch_device(args.device)
    print("model", model)
    print("transformers", transformers.__version__)
    print("torch", torch.__version__)
    print("cuda_available", torch.cuda.is_available())
    print("cuda_device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("cuda_device_0", torch.cuda.get_device_name(0))
    print("mode", args.mode)
    print("device", device)
    print("max_length", args.max_length)
    print("local_files_only", not args.allow_download)

    if args.mode == "embeddings":
        run_embeddings(args, model)
        return
    run_rerank(args, model)


if __name__ == "__main__":
    main()
