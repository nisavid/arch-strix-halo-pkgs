from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from gemma4_smoke_common import validate_basic_chat_text

SERVER_MODES = (
    "basic",
    "reasoning",
    "tool",
    "tool-thinking",
    "structured",
    "structured-thinking",
    "image",
    "multi-image",
    "image-dynamic",
    "audio",
    "video",
    "multimodal-tool",
    "full-feature-text-only",
    "benchmark-lite",
)
TOOL_MODES = {"tool", "tool-thinking", "multimodal-tool", "full-feature-text-only"}
REASONING_MODES = {
    "reasoning",
    "tool",
    "tool-thinking",
    "structured-thinking",
    "multimodal-tool",
    "full-feature-text-only",
}
STRUCTURED_MODES = {"structured", "structured-thinking"}
MULTIMODAL_MODES = {
    "image",
    "multi-image",
    "image-dynamic",
    "audio",
    "video",
    "multimodal-tool",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a local vLLM OpenAI-compatible server for a Gemma 4 -it model "
            "and run a basic, reasoning, or tool-calling smoke."
        )
    )
    parser.add_argument(
        "model",
        help="local model path or Hugging Face model id to serve",
    )
    parser.add_argument(
        "--mode",
        choices=SERVER_MODES,
        default="basic",
        help="which OpenAI-compatible server flow to validate",
    )
    parser.add_argument(
        "--served-model-name",
        help="served model name exposed through /v1/models; defaults to the model argument",
    )
    parser.add_argument(
        "--chat-template",
        type=Path,
        help=(
            "Gemma 4 tool chat template path; if omitted, --mode=tool requires "
            "a local model path that already ships chat_template.jinja"
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.75)
    parser.add_argument(
        "--max-num-batched-tokens",
        type=int,
        default=None,
        help=(
            "optional vLLM scheduler cap for model profiling and prefill batching; "
            "defaults to 32 for the validated Gemma 4 26B-A4B basic smoke lane"
        ),
    )
    parser.add_argument(
        "--max-model-len",
        type=int,
        default=None,
        help=(
            "server max model length; defaults to 512 for generic basic mode, "
            "128 for the validated Gemma 4 26B-A4B basic smoke lane, and "
            "1024 for reasoning/tool modes"
        ),
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=None,
        help=(
            "seconds to wait for /v1/models; defaults to 420 for the validated "
            "Gemma 4 26B-A4B basic lane and 180 otherwise"
        ),
    )
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument(
        "--execution-mode",
        choices=("eager", "compiled"),
        default="eager",
        help="use eager correctness mode or allow vLLM compilation/cudagraph paths",
    )
    parser.add_argument(
        "--no-enforce-eager",
        dest="execution_mode",
        action="store_const",
        const="compiled",
        help="alias for --execution-mode compiled",
    )
    parser.add_argument(
        "--moe-backend",
        choices=("auto", "triton", "aiter"),
        default="auto",
        help="optional vLLM MoE backend override",
    )
    parser.add_argument(
        "--attention-backend",
        help="optional vLLM attention backend override, for example TRITON_ATTN",
    )
    parser.add_argument("--async-scheduling", action="store_true")
    parser.add_argument("--kv-cache-dtype")
    parser.add_argument("--no-enable-prefix-caching", action="store_true")
    parser.add_argument("--max-num-seqs", type=int)
    parser.add_argument(
        "--limit-mm-per-prompt",
        help="JSON limit map passed to vLLM; defaults stay text-only except multimodal modes",
    )
    parser.add_argument(
        "--processor-kwargs",
        help="JSON object forwarded as --mm-processor-kwargs",
    )
    parser.add_argument(
        "--server-log",
        type=Path,
        default=Path("/tmp/gemma4-server-smoke.log"),
        help="log file for vLLM server stdout/stderr",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the derived server command and request payload as JSON without launching the server",
    )
    args = parser.parse_args()

    if args.mode in TOOL_MODES and args.chat_template is None:
        args.chat_template = default_tool_chat_template(args)
    if args.chat_template is not None:
        args.chat_template = args.chat_template.resolve()
    if args.mode in TOOL_MODES and not args.chat_template.is_file():
        parser.error(f"Gemma 4 tool chat template not found: {args.chat_template}")
    args.limit_mm_per_prompt_map = parse_json_object(
        args.limit_mm_per_prompt,
        option_name="--limit-mm-per-prompt",
    )
    args.processor_kwargs_map = parse_json_object(
        args.processor_kwargs,
        option_name="--processor-kwargs",
    )
    args.server_log = args.server_log.resolve()
    return args


def parse_json_object(raw: str | None, *, option_name: str) -> dict[str, object] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{option_name} must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{option_name} must decode to a JSON object")
    return value


def served_model_name(args: argparse.Namespace) -> str:
    return args.served_model_name or args.model


def default_tool_chat_template(args: argparse.Namespace) -> Path:
    model_path = Path(args.model)
    if model_path.exists():
        bundled_template = model_path / "chat_template.jinja"
        if bundled_template.is_file():
            return bundled_template.resolve()
    raise SystemExit(
        "--mode tool requires either --chat-template or a local model path "
        "that includes chat_template.jinja"
    )


def server_base_url(args: argparse.Namespace) -> str:
    return f"http://{args.host}:{args.port}"


def is_gemma4_26b_a4b(args: argparse.Namespace) -> bool:
    identifiers = (args.model, served_model_name(args))
    return any("gemma-4-26B-A4B-it" in identifier for identifier in identifiers)


def use_gemma4_26b_a4b_text_only_defaults(args: argparse.Namespace) -> bool:
    return args.mode == "basic" and is_gemma4_26b_a4b(args)


def effective_max_model_len(args: argparse.Namespace) -> int:
    if args.max_model_len is not None:
        return args.max_model_len
    if use_gemma4_26b_a4b_text_only_defaults(args):
        return 128
    if args.mode in REASONING_MODES or args.mode in STRUCTURED_MODES:
        return 1024
    return 512


def effective_max_num_batched_tokens(args: argparse.Namespace) -> int | None:
    if args.max_num_batched_tokens is not None:
        return args.max_num_batched_tokens
    if use_gemma4_26b_a4b_text_only_defaults(args):
        return 32
    return None


def effective_startup_timeout(args: argparse.Namespace) -> float:
    if args.startup_timeout is not None:
        return args.startup_timeout
    if use_gemma4_26b_a4b_text_only_defaults(args):
        return 420.0
    return 180.0


def effective_limit_mm_per_prompt(args: argparse.Namespace) -> dict[str, object]:
    if args.limit_mm_per_prompt_map is not None:
        return args.limit_mm_per_prompt_map
    if args.mode in {"image", "image-dynamic"}:
        return {"image": 1, "audio": 0, "video": 0}
    if args.mode == "multi-image":
        return {"image": 2, "audio": 0, "video": 0}
    if args.mode == "audio":
        return {"image": 0, "audio": 1, "video": 0}
    if args.mode == "video":
        return {"image": 0, "audio": 0, "video": 1}
    if args.mode == "multimodal-tool":
        return {"image": 1, "audio": 0, "video": 0}
    return {"image": 0, "audio": 0, "video": 0}


def compact_json(value: dict[str, object]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def build_server_command(args: argparse.Namespace) -> list[str]:
    limit_mm_per_prompt = compact_json(effective_limit_mm_per_prompt(args))
    max_model_len = effective_max_model_len(args)
    max_num_batched_tokens = effective_max_num_batched_tokens(args)
    command = [
        sys.executable,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        args.model,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--served-model-name",
        served_model_name(args),
        "--trust-remote-code",
        "--tensor-parallel-size",
        "1",
        "--gpu-memory-utilization",
        str(args.gpu_memory_utilization),
        "--max-model-len",
        str(max_model_len),
        "--limit-mm-per-prompt",
        limit_mm_per_prompt,
        "--disable-log-stats",
    ]
    if args.execution_mode == "eager":
        # Keep the tracked smoke on the validated eager correctness lane until
        # the compiled/cudagraph ROCm path is revalidated separately.
        command.append("--enforce-eager")
    if max_num_batched_tokens is not None:
        command.extend(
            [
                "--max-num-batched-tokens",
                str(max_num_batched_tokens),
            ]
        )
    if args.moe_backend != "auto":
        command.extend(["--moe-backend", args.moe_backend])
    if args.attention_backend:
        command.extend(["--attention-backend", args.attention_backend])
    if args.async_scheduling:
        command.append("--async-scheduling")
    if args.kv_cache_dtype:
        command.extend(["--kv-cache-dtype", args.kv_cache_dtype])
    if args.no_enable_prefix_caching or args.mode == "benchmark-lite":
        command.append("--no-enable-prefix-caching")
    if args.max_num_seqs is not None:
        command.extend(["--max-num-seqs", str(args.max_num_seqs)])
    if args.processor_kwargs_map is not None:
        command.extend(["--mm-processor-kwargs", compact_json(args.processor_kwargs_map)])
    if args.mode in REASONING_MODES:
        command.extend(["--reasoning-parser", "gemma4"])
    if args.mode in TOOL_MODES:
        command.extend(
            [
                "--tool-call-parser",
                "gemma4",
                "--enable-auto-tool-choice",
                "--chat-template",
                str(args.chat_template),
            ]
        )
    return command


def build_tool_spec() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather in a city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name to look up.",
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Requested temperature unit.",
                        },
                    },
                    "required": ["location"],
                },
            },
        }
    ]


def request_max_tokens(args: argparse.Namespace, desired: int) -> int:
    reserve = 64 if args.mode == "basic" else 128
    budget = max(1, effective_max_model_len(args) - reserve)
    return max(1, min(desired, budget))


def structured_response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "gemma4_smoke_answer",
            "schema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["topic", "answer"],
                "additionalProperties": False,
            },
        },
    }


def multimodal_content(args: argparse.Namespace) -> list[dict[str, object]]:
    if args.mode in {"image", "image-dynamic", "multimodal-tool"}:
        return [
            {"type": "text", "text": "Describe the image in five words."},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axX6n4AAAAASUVORK5CYII="
                },
            },
        ]
    if args.mode == "multi-image":
        return [
            {"type": "text", "text": "Compare these two tiny images in five words."},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axX6n4AAAAASUVORK5CYII="
                },
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axX6n4AAAAASUVORK5CYII="
                },
            },
        ]
    if args.mode == "audio":
        return [
            {"type": "text", "text": "Transcribe or summarize this audio briefly."},
            {
                "type": "input_audio",
                "input_audio": {
                    "data": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=",
                    "format": "wav",
                },
            },
        ]
    if args.mode == "video":
        return [
            {"type": "text", "text": "Describe this video in five words."},
            {
                "type": "video_url",
                "video_url": {
                    "url": "data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28ybXA0MQ=="
                },
            },
        ]
    raise ValueError(f"mode is not multimodal: {args.mode}")


def build_request_payload(args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": served_model_name(args),
        "messages": [],
        "max_tokens": request_max_tokens(args, 8 if args.mode == "benchmark-lite" else 16),
        "temperature": 0.0,
    }
    if args.mode in {"basic", "benchmark-lite"}:
        payload["messages"] = [
            {"role": "user", "content": "Write exactly five words about the ocean."}
        ]
        return payload
    if args.mode == "reasoning":
        payload["messages"] = [
            {
                "role": "user",
                "content": (
                    "A snail is at the bottom of a 20-foot well. "
                    "Each day it climbs 3 feet and each night it slides back 2 feet. "
                    "How many days does it take to reach the top?"
                ),
            }
        ]
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        payload["max_tokens"] = request_max_tokens(args, 1024)
        payload["skip_special_tokens"] = False
        return payload
    if args.mode in STRUCTURED_MODES:
        payload["messages"] = [
            {
                "role": "user",
                "content": "Return JSON about the ocean with topic and answer fields.",
            }
        ]
        payload["response_format"] = structured_response_format()
        if args.mode == "structured-thinking":
            payload["chat_template_kwargs"] = {"enable_thinking": True}
            payload["skip_special_tokens"] = False
            payload["max_tokens"] = request_max_tokens(args, 1024)
        return payload
    if args.mode in MULTIMODAL_MODES:
        payload["messages"] = [{"role": "user", "content": multimodal_content(args)}]
        if args.mode == "multimodal-tool":
            payload["tools"] = build_tool_spec()
            payload["tool_choice"] = "auto"
            payload["chat_template_kwargs"] = {"enable_thinking": True}
            payload["max_tokens"] = request_max_tokens(args, 512)
            payload["skip_special_tokens"] = False
        return payload

    payload["messages"] = [
        {"role": "user", "content": "What is the weather in Tokyo today? Use the tool."}
    ]
    payload["tools"] = build_tool_spec()
    payload["tool_choice"] = "auto"
    payload["max_tokens"] = request_max_tokens(args, 512)
    payload["skip_special_tokens"] = False
    if args.mode in {"tool-thinking", "full-feature-text-only"}:
        payload["chat_template_kwargs"] = {"enable_thinking": True}
    if args.mode == "full-feature-text-only":
        payload["response_format"] = structured_response_format()
    return payload


def build_tool_followup_payload(
    args: argparse.Namespace,
    assistant_message: dict[str, Any],
) -> dict[str, object]:
    tool_calls = assistant_message.get("tool_calls") or []
    if not tool_calls:
        raise RuntimeError("tool mode response did not include any tool_calls")
    tool_call = tool_calls[0]
    return {
        "model": served_model_name(args),
        "messages": [
            {"role": "user", "content": "What is the weather in Tokyo today? Use the tool."},
            assistant_message,
            {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(
                    {
                        "temperature": 22,
                        "condition": "Partly cloudy",
                        "unit": "celsius",
                    },
                    sort_keys=True,
                ),
            },
        ],
        "tools": build_tool_spec(),
        "max_tokens": request_max_tokens(args, 512),
        "skip_special_tokens": False,
        "temperature": 0.0,
    }


def build_plan(args: argparse.Namespace) -> dict[str, object]:
    request_payload = build_request_payload(args)
    plan: dict[str, object] = {
        "mode": args.mode,
        "model": args.model,
        "served_model_name": served_model_name(args),
        "execution_mode": args.execution_mode,
        "server_command": build_server_command(args),
        "startup_timeout": effective_startup_timeout(args),
        "models_url": f"{server_base_url(args)}/v1/models",
        "request_url": f"{server_base_url(args)}/v1/chat/completions",
        "request_payload": request_payload,
        "server_log": str(args.server_log),
    }
    if args.mode in TOOL_MODES:
        plan["followup_request_payload"] = build_tool_followup_payload(
            args,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_gemma4_weather",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location":"Tokyo","unit":"celsius"}',
                        },
                    }
                ],
            },
        )
    return plan


def post_json(url: str, api_key: str, payload: dict[str, object], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_server(
    process: subprocess.Popen[str],
    models_url: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early with return code {process.returncode}")
        try:
            return get_json(models_url, timeout=5.0)
        except urllib.error.URLError:
            time.sleep(1.0)
    raise RuntimeError(f"timed out waiting for {models_url}")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=10.0)


def extract_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"response did not include any choices: {json.dumps(response, sort_keys=True)}")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"response choice did not include a message: {json.dumps(response, sort_keys=True)}")
    return message


def validate_basic_response(response: dict[str, Any]) -> dict[str, Any]:
    message = extract_message(response)
    validate_basic_chat_text(message.get("content") or "")
    return message


def validate_reasoning_response(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"response did not include any choices: {json.dumps(response, sort_keys=True)}")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"response choice did not include a message: {json.dumps(response, sort_keys=True)}")
    content = (message.get("content") or "").strip()
    reasoning = message.get("reasoning") or message.get("reasoning_content")
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length" and not reasoning and content.startswith("thought"):
        raise RuntimeError(
            "reasoning response truncated inside the Gemma 4 thought block; "
            "increase --max-model-len and rerun"
        )
    if not content and not reasoning:
        raise RuntimeError("reasoning mode response had neither content nor reasoning output")
    return message


def validate_tool_response(response: dict[str, Any]) -> dict[str, Any]:
    message = extract_message(response)
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        raise RuntimeError("tool mode response did not include a tool call")
    function = tool_calls[0].get("function") or {}
    if function.get("name") != "get_weather":
        raise RuntimeError(f"unexpected tool call: {json.dumps(tool_calls[0], sort_keys=True)}")
    return message


def validate_structured_response(response: dict[str, Any]) -> dict[str, Any]:
    message = extract_message(response)
    raw_content = message.get("content") or ""
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"structured response was not JSON: {raw_content!r}") from exc
    if not isinstance(payload, dict) or not {"topic", "answer"}.issubset(payload):
        raise RuntimeError(f"structured response did not match smoke schema: {payload!r}")
    return message


def tail_log(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])


def run_smoke(args: argparse.Namespace) -> None:
    plan = build_plan(args)
    print("mode", args.mode)
    print("model", args.model)
    print("served_model_name", served_model_name(args))
    print("server_log", str(args.server_log))
    print("startup_timeout", plan["startup_timeout"])
    print("server_command", json.dumps(plan["server_command"]))

    args.server_log.parent.mkdir(parents=True, exist_ok=True)
    with args.server_log.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            plan["server_command"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            models_payload = wait_for_server(
                process,
                str(plan["models_url"]),
                float(plan["startup_timeout"]),
            )
            print("server_ready")
            print("models_payload", json.dumps(models_payload, sort_keys=True))

            response = post_json(
                str(plan["request_url"]),
                args.api_key,
                dict(plan["request_payload"]),
                args.request_timeout,
            )
            print("initial_response", json.dumps(response, sort_keys=True))

            if args.mode in {"basic", "benchmark-lite"}:
                validate_basic_response(response)
                print("benchmark_lite_ok" if args.mode == "benchmark-lite" else "basic_ok")
            elif args.mode == "reasoning":
                message = validate_reasoning_response(response)
                print("reasoning_field_present", bool(message.get("reasoning") or message.get("reasoning_content")))
                print("reasoning_ok")
            elif args.mode in STRUCTURED_MODES:
                message = validate_structured_response(response)
                print("reasoning_field_present", bool(message.get("reasoning") or message.get("reasoning_content")))
                print("structured_ok")
            elif args.mode in TOOL_MODES:
                assistant_message = validate_tool_response(response)
                followup_payload = build_tool_followup_payload(args, assistant_message)
                followup = post_json(
                    str(plan["request_url"]),
                    args.api_key,
                    followup_payload,
                    args.request_timeout,
                )
                print("followup_response", json.dumps(followup, sort_keys=True))
                validate_basic_response(followup)
                print("tool_ok")
            else:
                validate_basic_response(response)
                print(f"{args.mode}_ok")
        except Exception:
            print("server_log_tail_start", file=sys.stderr)
            tail = tail_log(args.server_log)
            if tail:
                print(tail, file=sys.stderr)
            print("server_log_tail_end", file=sys.stderr)
            raise
        finally:
            terminate_process(process)


def main() -> None:
    args = parse_args()
    plan = build_plan(args)
    if args.dry_run:
        json.dump(plan, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return
    run_smoke(args)


if __name__ == "__main__":
    main()
