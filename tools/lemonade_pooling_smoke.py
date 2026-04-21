#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
from typing import Any, Iterable
from urllib import error, request


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
    parser = argparse.ArgumentParser(description="Run a Lemonade endpoint pooling smoke.")
    parser.add_argument("model", help="Lemonade model id")
    parser.add_argument(
        "--mode",
        choices=("embeddings", "rerank"),
        required=True,
        help="Lemonade endpoint fixture to run",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:13305/api/v1",
        help="Lemonade API base URL",
    )
    parser.add_argument("--request-timeout", type=float, default=300.0)
    return parser.parse_args()


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        print(response_body)
        raise
    if "error" in payload:
        print(json.dumps(payload, sort_keys=True))
        message = payload["error"].get("message", "unknown Lemonade error")
        raise AssertionError(f"lemonade_error: {message}")
    return payload


def embedding_vectors(payload: dict[str, Any]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for item in payload.get("data", []):
        vectors.append([float(value) for value in item["embedding"]])
    return vectors


def rerank_scores(payload: dict[str, Any]) -> list[float]:
    results = payload.get("results", [])
    by_index = {int(item["index"]): float(item["relevance_score"]) for item in results}
    return [by_index[index] for index in sorted(by_index)]


def _assert_finite_values(values: Iterable[float], *, label: str) -> None:
    for index, value in enumerate(values):
        if not math.isfinite(value):
            raise AssertionError(f"{label}_{index}_not_finite: {value!r}")


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

    print("embedding_count", len(vectors))
    print("embedding_dim", dimension)
    print("embeddings_finite_ok")


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


def run_embeddings(args: argparse.Namespace) -> None:
    payload = _post_json(
        f"{args.base_url.rstrip('/')}/embeddings",
        {"model": args.model, "input": EMBEDDING_PROMPTS},
        timeout=args.request_timeout,
    )
    vectors = embedding_vectors(payload)
    validate_embedding_fixture(vectors)
    print("embeddings_ok")


def run_rerank(args: argparse.Namespace) -> None:
    payload = _post_json(
        f"{args.base_url.rstrip('/')}/reranking",
        {
            "model": args.model,
            "query": RERANK_QUERY,
            "documents": RERANK_DOCUMENTS,
        },
        timeout=args.request_timeout,
    )
    scores = rerank_scores(payload)
    validate_rerank_fixture(scores)
    print("rerank_ok")


def main() -> None:
    args = parse_args()
    print("lemonade_base_url", args.base_url.rstrip("/"))
    print("model", args.model)
    print("mode", args.mode)
    if args.mode == "embeddings":
        run_embeddings(args)
        return
    run_rerank(args)


if __name__ == "__main__":
    main()
