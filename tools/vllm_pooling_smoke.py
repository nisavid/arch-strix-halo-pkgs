from __future__ import annotations

import argparse
import importlib.metadata as metadata
import math
from pathlib import Path
from typing import Any, Iterable


EMBEDDING_PROMPTS = [
    "query: Which city is the capital of France?",
    "passage: Paris is the capital city of France.",
    "passage: Bread dough rises when yeast ferments sugar.",
]

RERANK_QUERY = "Which city is the capital of France?"
RERANK_DOCUMENTS = [
    "Paris is the capital city of France and home to the Eiffel Tower.",
    "Berlin is the capital city of Germany.",
    "Bread dough rises when yeast ferments sugar.",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a vLLM pooling smoke.")
    parser.add_argument("model", help="local model path or Hugging Face model id")
    parser.add_argument(
        "--mode",
        choices=("embeddings", "rerank"),
        required=True,
        help="pooling task fixture to run",
    )
    parser.add_argument("--attention-backend", default="FLEX_ATTENTION")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.5)
    parser.add_argument("--max-model-len", type=int, default=256)
    parser.add_argument("--max-num-batched-tokens", type=int, default=None)
    return parser.parse_args()


def resolved_model_arg(model: str) -> str:
    path = Path(model)
    if path.exists():
        return str(path.resolve())
    return model


def _as_float_list(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def embedding_vector(output: Any) -> list[float]:
    outputs = output.outputs
    if hasattr(outputs, "embedding"):
        return _as_float_list(outputs.embedding)
    if hasattr(outputs, "data"):
        return _as_float_list(outputs.data)
    raise AssertionError(f"unsupported embedding output shape: {outputs!r}")


def score_value(output: Any) -> float:
    outputs = output.outputs
    if hasattr(outputs, "score"):
        return float(outputs.score)
    if hasattr(outputs, "data"):
        data = outputs.data
        if hasattr(data, "squeeze"):
            data = data.squeeze()
        if hasattr(data, "item"):
            return float(data.item())
        return float(data)
    raise AssertionError(f"unsupported scoring output shape: {outputs!r}")


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


def _llm_kwargs(args: argparse.Namespace, model: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "runner": "pooling",
        "trust_remote_code": True,
        "max_model_len": args.max_model_len,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "tensor_parallel_size": 1,
        "disable_log_stats": True,
        "enforce_eager": True,
        "attention_config": {"backend": args.attention_backend},
    }
    if args.mode == "rerank":
        kwargs["convert"] = "classify"
        kwargs["pooler_config"] = {"task": "classify"}
    if args.max_num_batched_tokens is not None:
        kwargs["max_num_batched_tokens"] = args.max_num_batched_tokens
    return kwargs


def classification_pooling_params() -> Any:
    from vllm.pooling_params import PoolingParams

    return PoolingParams(task="classify")


def run_embeddings(llm: Any) -> None:
    outputs = llm.embed(EMBEDDING_PROMPTS, use_tqdm=False)
    vectors = [embedding_vector(output) for output in outputs]
    validate_embedding_fixture(vectors)
    print("embeddings_ok")


def run_rerank(llm: Any) -> None:
    outputs = llm.score(
        RERANK_QUERY,
        RERANK_DOCUMENTS,
        use_tqdm=False,
        pooling_params=classification_pooling_params(),
    )
    scores = [score_value(output) for output in outputs]
    validate_rerank_fixture(scores)
    print("rerank_ok")


def main() -> None:
    args = parse_args()
    model = resolved_model_arg(args.model)

    import torch
    from vllm import LLM

    print("model", model)
    print("vllm", metadata.version("vllm"))
    print("torch", torch.__version__)
    print("cuda_available", torch.cuda.is_available())
    print("cuda_device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("cuda_device_0", torch.cuda.get_device_name(0))
    print("runner pooling")
    print("mode", args.mode)
    print("attention_backend", args.attention_backend)
    print("gpu_memory_utilization", args.gpu_memory_utilization)
    print("max_model_len", args.max_model_len)
    print("max_num_batched_tokens", args.max_num_batched_tokens)
    if args.mode == "rerank":
        print("pooling_task classify")
        print("convert classify")

    llm = LLM(**_llm_kwargs(args, model))
    print("llm_init_ok")

    if args.mode == "embeddings":
        run_embeddings(llm)
        return
    run_rerank(llm)


if __name__ == "__main__":
    main()
