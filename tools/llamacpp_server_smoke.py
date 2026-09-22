#!/usr/bin/env python3
"""Serve one GGUF file with a packaged llama-server and check a text completion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import subprocess
import time
from typing import Any
from urllib import error, request


COMPLETION_PROMPT = "The capital of France is"
COMPLETION_EXPECTED = "paris"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_path", type=Path, help="local GGUF file")
    parser.add_argument("--server", required=True, help="packaged llama-server entrypoint")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--server-log", type=Path)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--request-timeout", type=float, default=300.0)
    return parser.parse_args()


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if payload is None else {"Content-Type": "application/json"}
    req = request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    with request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def server_command(args: argparse.Namespace) -> list[str]:
    return [
        args.server,
        "-m",
        str(args.model_path),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "-c",
        str(args.ctx_size),
        "-ngl",
        "999",
    ]


def completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise AssertionError(f"completion returned no choices: {payload!r}")
    return str(choices[0].get("text", ""))


def validate_completion(text: str) -> None:
    if COMPLETION_EXPECTED not in text.lower():
        raise AssertionError(f"completion did not mention Paris: {text!r}")


def _wait_for_health(base_url: str, proc: subprocess.Popen, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited during startup with {proc.returncode}")
        try:
            _request_json(f"{base_url}/health", timeout=5.0)
            return
        except (error.URLError, OSError, ValueError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise TimeoutError(f"llama-server did not become healthy: {last_error}")


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=15.0)


def run_smoke(args: argparse.Namespace) -> None:
    if not args.model_path.is_file():
        raise FileNotFoundError(f"GGUF model binding is not a file: {args.model_path}")
    if args.port == 0:
        args.port = _free_port(args.host)
    base_url = f"http://{args.host}:{args.port}"

    log_handle = None
    stdout: Any = subprocess.DEVNULL
    if args.server_log is not None:
        args.server_log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.server_log.open("w", encoding="utf-8")
        stdout = log_handle
    try:
        proc = subprocess.Popen(
            server_command(args),
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_for_health(base_url, proc, timeout=args.startup_timeout)
            print("server", args.server)
            print("server_ready")
            payload = _request_json(
                f"{base_url}/v1/completions",
                payload={
                    "prompt": COMPLETION_PROMPT,
                    "max_tokens": 8,
                    "temperature": 0,
                },
                timeout=args.request_timeout,
            )
            text = completion_text(payload)
            print("completion_text", json.dumps(text))
            validate_completion(text)
            print("completion_ok")
        finally:
            _stop(proc)
    finally:
        if log_handle is not None:
            log_handle.close()


def main() -> None:
    run_smoke(parse_args())


if __name__ == "__main__":
    main()
