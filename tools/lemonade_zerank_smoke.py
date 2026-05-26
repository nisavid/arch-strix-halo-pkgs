#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any
from urllib import error, request


CAPITAL_FRANCE_QUERY = "capital of France"
CAPITAL_FRANCE_DOCUMENTS = [
    "Paris is the capital of France.",
    "apple",
    "dog",
    "tomato",
]

ARITHMETIC_QUERY = "What is 2+2?"
ARITHMETIC_DOCUMENTS = [
    "Two plus two equals four.",
    "4",
    "The answer is definitely 1 million.",
]

ADAPTER_OPTIONS = {
    "llamacpp_reranking_adapter": "zeroentropy-logit-score",
    "llamacpp_reranking_true_token_id": 9454,
    "llamacpp_reranking_logit_scale": 5.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Lemonade zerank-2 selected-logit integration smoke."
    )
    parser.add_argument("model", help="Lemonade model id")
    parser.add_argument(
        "--base-url",
        help="Existing Lemonade API base URL. If omitted, starts an isolated lemond.",
    )
    parser.add_argument("--lemond", default="/usr/bin/lemond")
    parser.add_argument("--llama-server", default="/usr/bin/llama-server-hip-gfx1151")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--server-log", type=Path)
    parser.add_argument("--startup-timeout", type=float, default=120.0)
    parser.add_argument("--request-timeout", type=float, default=600.0)
    return parser.parse_args()


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(body)
        raise
    result = json.loads(body) if body else {}
    if "error" in result:
        print(json.dumps(result, sort_keys=True))
        raise AssertionError(f"lemonade_error: {_error_payload_message(result['error'])}")
    return result


def _error_payload_message(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("message", payload))
    return str(payload)


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _write_config(cache_dir: Path, *, port: int, host: str, llama_server: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "host": host,
        "port": port,
        "log_level": "debug",
        "max_loaded_models": 1,
        "no_broadcast": True,
        "no_fetch_executables": False,
        "llamacpp": {
            "backend": "rocm",
            "prefer_system": True,
            "rocm_bin": llama_server,
            "vulkan_bin": "builtin",
            "cpu_bin": "builtin",
        },
    }
    (cache_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")


def _start_lemond(args: argparse.Namespace) -> tuple[subprocess.Popen, Path | None, Any]:
    if args.port == 0:
        args.port = _free_port(args.host)

    owned_cache_dir = args.cache_dir is None
    cache_dir = args.cache_dir or Path(tempfile.mkdtemp(prefix="lemonade-zerank-"))
    _write_config(cache_dir, port=args.port, host=args.host, llama_server=args.llama_server)

    log_handle = None
    stdout = subprocess.DEVNULL
    if args.server_log is not None:
        args.server_log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.server_log.open("w", encoding="utf-8")
        stdout = log_handle

    env = os.environ.copy()
    env["LEMONADE_NO_BROADCAST"] = "true"
    env["LEMONADE_LLAMACPP_ROCM_BIN"] = args.llama_server
    env["LEMONADE_LLAMACPP_ROCM_LABEL"] = "System llama-server-hip-gfx1151"
    try:
        proc = subprocess.Popen(
            [
                args.lemond,
                str(cache_dir),
                "--host",
                args.host,
                "--port",
                str(args.port),
            ],
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
    except Exception:
        if log_handle is not None:
            log_handle.close()
        if owned_cache_dir:
            shutil.rmtree(cache_dir, ignore_errors=True)
        raise
    print("isolated_server_started")
    return proc, cache_dir if owned_cache_dir else None, log_handle


def _wait_for_health(base_url: str, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _request_json(f"{base_url}/health", timeout=5.0)
            return
        except Exception as exc:  # noqa: BLE001 - startup retries surface final cause.
            last_error = exc
            time.sleep(0.5)
    raise TimeoutError(f"lemond did not become healthy: {last_error}")


def _shutdown(root_url: str, *, timeout: float) -> None:
    try:
        _request_json(f"{root_url}/internal/shutdown", method="POST", timeout=timeout)
    except Exception:
        pass


def _coerce_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def validate_model_metadata(payload: dict[str, Any]) -> None:
    model = _coerce_model_payload(payload)
    labels = set(model.get("labels", []))
    options = model.get("recipe_options", {})

    if "reranking" not in labels:
        raise AssertionError(f"zerank-2-GGUF missing reranking label: {sorted(labels)}")
    if model.get("recipe") != "llamacpp":
        raise AssertionError(f"zerank-2-GGUF expected llamacpp recipe: {model.get('recipe')!r}")

    for key, expected in ADAPTER_OPTIONS.items():
        actual = options.get(key)
        if actual != expected:
            raise AssertionError(
                f"zerank-2-GGUF missing adapter option {key}: expected {expected!r}, got {actual!r}"
            )


def _assert_finite_nonzero(scores_by_document: dict[str, float], *, label: str) -> None:
    for document, score in scores_by_document.items():
        if not math.isfinite(score):
            raise AssertionError(f"{label} score for {document!r} is not finite: {score!r}")
        if score == 0:
            raise AssertionError(f"{label} score for {document!r} is zero")


def _ordered_documents(scores_by_document: dict[str, float]) -> list[str]:
    return sorted(scores_by_document, key=scores_by_document.__getitem__, reverse=True)


def validate_capital_france_fixture(scores_by_document: dict[str, float]) -> None:
    _assert_finite_nonzero(scores_by_document, label="capital_france")
    ordered = _ordered_documents(scores_by_document)
    if ordered[0] != "Paris is the capital of France.":
        raise AssertionError(f"expected Paris first for capital France fixture, got {ordered!r}")


def validate_arithmetic_fixture(scores_by_document: dict[str, float]) -> None:
    _assert_finite_nonzero(scores_by_document, label="arithmetic")
    ordered = _ordered_documents(scores_by_document)
    expected = [
        "Two plus two equals four.",
        "4",
        "The answer is definitely 1 million.",
    ]
    if ordered != expected:
        raise AssertionError(f"expected arithmetic ordering {expected!r}, got {ordered!r}")


def _scores_by_document(payload: dict[str, Any], documents: list[str]) -> dict[str, float]:
    results = payload.get("results", [])
    if len(results) != len(documents):
        raise AssertionError(f"score_count expected {len(documents)}, got {len(results)}")
    scores: dict[str, float] = {}
    seen_indices: set[int] = set()
    for item in results:
        index = int(item["index"])
        if index < 0 or index >= len(documents):
            raise AssertionError(f"result index out of bounds: {index}")
        if index in seen_indices:
            raise AssertionError(f"duplicate result index: {index}")
        seen_indices.add(index)
        scores[documents[index]] = float(item["relevance_score"])
    return scores


def _rerank(
    base_url: str,
    *,
    model: str,
    query: str,
    documents: list[str],
    timeout: float,
) -> dict[str, float]:
    payload = _request_json(
        f"{base_url}/reranking",
        method="POST",
        payload={"model": model, "query": query, "documents": documents},
        timeout=timeout,
    )
    return _scores_by_document(payload, documents)


def _validate_health(base_url: str, *, model: str, timeout: float) -> None:
    payload = _request_json(f"{base_url}/health", timeout=timeout)
    loaded = payload.get("all_models_loaded", [])
    match = next(
        (
            item
            for item in loaded
            if item.get("model_name") in {model, f"user.{model}"}
            or item.get("id") in {model, f"user.{model}"}
        ),
        None,
    )
    if match is None:
        raise AssertionError(f"zerank loaded model missing from health: {loaded!r}")
    options = match.get("recipe_options", {})
    for key, expected in ADAPTER_OPTIONS.items():
        actual = options.get(key)
        if actual != expected:
            raise AssertionError(
                f"health missing adapter option {key}: expected {expected!r}, got {actual!r}"
            )


def _stop_lemond(root_url: str, proc: Any) -> None:
    _shutdown(root_url, timeout=10.0)
    try:
        proc.wait(timeout=15.0)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=15.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                pass


def run_smoke(args: argparse.Namespace) -> None:
    root_url = None
    proc = None
    owned_cache_dir = None
    log_handle = None
    try:
        if args.base_url is None:
            proc, owned_cache_dir, log_handle = _start_lemond(args)
            root_url = f"http://{args.host}:{args.port}"
            base_url = f"{root_url}/api/v1"
            _wait_for_health(base_url, timeout=args.startup_timeout)
        else:
            base_url = args.base_url.rstrip("/")
            root_url = base_url.removesuffix("/api/v1").removesuffix("/v1")

        print("model", args.model)
        print("mode selected-logit")

        metadata = _request_json(
            f"{base_url}/models/{args.model}",
            timeout=args.request_timeout,
        )
        validate_model_metadata(metadata)
        print("zerank_adapter_options_ok")

        capital_scores = _rerank(
            base_url,
            model=args.model,
            query=CAPITAL_FRANCE_QUERY,
            documents=CAPITAL_FRANCE_DOCUMENTS,
            timeout=args.request_timeout,
        )
        validate_capital_france_fixture(capital_scores)
        print("capital_france_order_ok")

        arithmetic_scores = _rerank(
            base_url,
            model=args.model,
            query=ARITHMETIC_QUERY,
            documents=ARITHMETIC_DOCUMENTS,
            timeout=args.request_timeout,
        )
        validate_arithmetic_fixture(arithmetic_scores)
        print("arithmetic_order_ok")

        _validate_health(base_url, model=args.model, timeout=args.request_timeout)
        print("health_adapter_options_ok")
        print("zerank_rerank_ok")
    finally:
        if root_url is not None and proc is not None:
            _stop_lemond(root_url, proc)
        if log_handle is not None:
            log_handle.close()
        if owned_cache_dir is not None:
            shutil.rmtree(owned_cache_dir, ignore_errors=True)


def main() -> None:
    run_smoke(parse_args())


if __name__ == "__main__":
    main()
