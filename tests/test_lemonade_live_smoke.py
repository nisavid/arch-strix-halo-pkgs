from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import lemonade_live_smoke as live
from lemonade_api_auth import auth_headers, resolve_admin_api_key, resolve_api_key
from llamacpp_server_smoke import (
    completion_text,
    server_command,
    validate_completion,
    verify_sha256,
)


MODEL = "user.Qwen3-0.6B-Q8_0-GGUF"
PINNED_SHA256 = "9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031"
SERVICE_GGUF = Path("/service-cache/Qwen3-0.6B-Q8_0.gguf")
EXTRA_A = "extra.lemonade-live-a.gguf"
EXTRA_B = "extra.lemonade-live-b.gguf"


def test_api_key_resolution_prefers_credential_file_and_admin_falls_back(tmp_path: Path):
    key_file = tmp_path / "lemonade-key"
    key_file.write_text("file-key\n", encoding="utf-8")

    assert resolve_api_key({}) is None
    assert resolve_api_key({"LEMONADE_API_KEY": "env-key"}) == "env-key"
    assert (
        resolve_api_key({"LEMONADE_API_KEY": "env-key", "LEMONADE_API_KEY_FILE": str(key_file)})
        == "file-key"
    )
    assert resolve_admin_api_key({"LEMONADE_API_KEY": "env-key"}) == "env-key"
    assert (
        resolve_admin_api_key({"LEMONADE_API_KEY": "env-key", "LEMONADE_ADMIN_API_KEY": "admin"})
        == "admin"
    )
    assert auth_headers(None) == {}
    assert auth_headers("k") == {"Authorization": "Bearer k"}

    key_file.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty credential file"):
        resolve_api_key({"LEMONADE_API_KEY_FILE": str(key_file)})


def test_client_sends_admin_key_only_to_internal_endpoints():
    client = live.LemonadeClient(
        "http://127.0.0.1:13305/api/v1", api_key="regular", admin_api_key="admin"
    )

    api_request = client._request_obj("GET", "/health", None)
    internal_request = client._request_obj("GET", "/internal/config", None)

    assert api_request.full_url == "http://127.0.0.1:13305/api/v1/health"
    assert api_request.get_header("Authorization") == "Bearer regular"
    assert internal_request.full_url == "http://127.0.0.1:13305/internal/config"
    assert internal_request.get_header("Authorization") == "Bearer admin"
    ollama_request = client._request_obj("POST", "/api/chat", {"model": "m:latest"})
    assert ollama_request.full_url == "http://127.0.0.1:13305/api/chat"
    assert ollama_request.get_header("Authorization") == "Bearer regular"


def test_failures_are_reported_without_host_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    cached = tmp_path / "cache" / "bin" / "llama-server"

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr=f"error: No package owns {cached}")

    with pytest.raises(AssertionError) as excinfo:
        live.package_owner(cached, runner=runner)
    assert str(tmp_path) not in str(excinfo.value)

    def failing_main(argv=None):
        raise AssertionError(f"backend process is owned by nothing at {cached}")

    monkeypatch.setattr(live, "main", failing_main)
    assert live.run_cli([]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: AssertionError: backend process is owned by nothing at <path>")
    assert str(tmp_path) not in err
    assert "Traceback" not in err


def test_scrub_paths_hides_cache_and_host_paths_but_keeps_packaged_bins(tmp_path: Path):
    cache = tmp_path / "hf-cache"
    text = (
        f"open {cache}/models--x/blobs/abc failed; backend {tmp_path}/lemonade/bin/llama-server; "
        "exe /usr/bin/lemond; home /home/user/.cache/x; url http://127.0.0.1:9/api/models; ratio 1/2"
    )

    scrubbed = live.scrub_paths(text, {"model_cache": cache})

    assert str(tmp_path) not in scrubbed
    assert "open <model_cache> failed" in scrubbed
    assert "backend <path>;" in scrubbed
    assert "/usr/bin/lemond" in scrubbed
    assert "home <path>;" in scrubbed
    assert "http://127.0.0.1:9/api/models" in scrubbed
    assert "ratio 1/2" in scrubbed


def test_pooling_smoke_sends_optional_api_key(monkeypatch: pytest.MonkeyPatch):
    import lemonade_pooling_smoke

    seen: dict[str, Any] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def read(self):
            return b'{"data": []}'

    def fake_urlopen(req, timeout):
        seen["authorization"] = req.get_header("Authorization")
        return Response()

    monkeypatch.setenv("LEMONADE_API_KEY", "loopback-key")
    monkeypatch.setattr(lemonade_pooling_smoke.request, "urlopen", fake_urlopen)

    lemonade_pooling_smoke._post_json("http://127.0.0.1:13305/api/v1/embeddings", {}, timeout=1.0)

    assert seen["authorization"] == "Bearer loopback-key"


def test_llamacpp_server_command_offloads_all_layers_and_completion_checks_paris():
    args = argparse.Namespace(
        server="llama-server-hip-gfx1151",
        model_path=Path("/models/Qwen3-0.6B-Q8_0.gguf"),
        host="127.0.0.1",
        port=8080,
        ctx_size=4096,
    )

    assert server_command(args) == [
        "llama-server-hip-gfx1151",
        "-m",
        "/models/Qwen3-0.6B-Q8_0.gguf",
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "-c",
        "4096",
        "-ngl",
        "999",
    ]
    assert completion_text({"choices": [{"text": " Paris."}]}) == " Paris."
    validate_completion(" Paris.")
    with pytest.raises(AssertionError, match="Paris"):
        validate_completion(" Lyon.")


def test_refusal_and_system_info_parsers():
    message = (
        "Predicted GPU memory occupancy 431.2 GB for requested model cannot fit "
        "within effective capacity 96.5 GB"
    )
    assert live.refusal_capacity_gb(message) == 96.5
    assert live.refusal_capacity_gb("All loaded models of type llm are pinned.") is None
    assert live.error_message({"error": {"message": "nope"}}) == "nope"
    assert live.error_message({"status": "error", "message": "bad"}) == "bad"
    assert live.error_message({"status": "success"}) is None

    system_info = {
        "devices": {
            "amd_gpu": [
                {"name": "dGPU", "available": True, "gpu_type": "discrete", "family": "gfx1100"},
                {
                    "name": "AMD Radeon 8060S",
                    "available": True,
                    "gpu_type": "integrated",
                    "family": "gfx1151",
                    "vram_gb": 0.5,
                    "virtual_mem_gb": 110.0,
                },
            ]
        },
        "recipes": {
            "llamacpp": {"backends": {"rocm": {"state": "installed", "devices": ["amd_gpu"]}}}
        },
    }
    assert live.validate_hip_discovery(system_info, expect_family="gfx1151")["family"] == "gfx1151"
    with pytest.raises(AssertionError, match="expected GPU family"):
        live.validate_hip_discovery(system_info, expect_family="gfx1150")
    system_info["recipes"]["llamacpp"]["backends"]["rocm"]["state"] = "installable"
    with pytest.raises(AssertionError, match="not installed"):
        live.validate_hip_discovery(system_info, expect_family="gfx1151")


def test_parse_pacman_info_and_process_executable(tmp_path: Path):
    info = live.parse_pacman_info(
        "Name            : lemonade-server\n"
        "Version         : 11.7.0-1\n"
        "Depends On      : glibc\n"
        "                  llama.cpp\n"
        "Packager        : Example Packager <packager@example.invalid>\n"
    )
    assert info["Version"] == "11.7.0-1"
    assert info["Depends On"] == "glibc llama.cpp"
    assert info["Packager"].startswith("Example Packager")

    (tmp_path / "42").mkdir()
    (tmp_path / "42" / "cmdline").write_bytes(
        b"/opt/llama.cpp-hip-gfx1151/bin/llama-server\0-m\0model.gguf\0"
    )
    assert (
        live.process_executable(42, proc_root=tmp_path)
        == "/opt/llama.cpp-hip-gfx1151/bin/llama-server"
    )


def test_isolated_config_is_offline_and_uses_packaged_backends(tmp_path: Path):
    config = live.isolated_config(
        host="127.0.0.1",
        port=13999,
        models_dir=tmp_path / "models",
        extra_models_dir=tmp_path / "extra",
        backend_bins=live.DEFAULT_BACKEND_BINS,
    )

    assert config["offline"] is True
    assert config["no_fetch_executables"] is True
    assert config["broadcast"] is False
    assert config["max_loaded_models"] == 1
    assert config["pinned_models"] == []
    assert config["llamacpp"]["rocm_bin"] == "/opt/llama.cpp-hip-gfx1151/bin"
    assert config["llamacpp"]["vulkan_bin"] == "/opt/llama.cpp-vulkan-gfx1151/bin"


def test_isolated_lemond_cleans_up_when_startup_fails(tmp_path: Path):
    args = live.parse_args(
        ["lifecycle", "--lemond", "/bin/false", "--server-log", str(tmp_path / "server.log")]
    )
    inst = live.IsolatedLemond(args)

    with pytest.raises(RuntimeError, match="exited during startup"):
        with inst:
            pass

    assert inst.root is not None
    assert not inst.root.exists()
    assert inst.proc is not None and inst.proc.poll() is not None


class FakeLemond:
    """A small in-memory lemond that honors pins, busy models, one slot, and a budget."""

    def __init__(self, *, models: list[str], capacity_gb: float = 96.5) -> None:
        self.models = {name: {"id": name, "downloaded": True, "checkpoint": "Qwen/Qwen3-0.6B-GGUF:Q8_0", "recipe": "llamacpp"} for name in models}
        self.loaded: dict[str, dict[str, Any]] = {}
        self.config: dict[str, Any] = {
            "global_timeout": 600,
            "pinned_models": [],
            "max_gpu_memory_occupancy_gb": -1.0,
            "offline": True,
            "no_fetch_executables": True,
        }
        self.capacity_gb = capacity_gb
        self.next_pid = 100
        self.calls: list[tuple[str, str]] = []
        self.timeout = 5.0
        self.busy_model: str | None = None
        self.model_storage = Path("/service-hf-cache")
        self.auto_pull = False
        # Request paths on which an absent model is fetched instead of refused.
        self.auto_pull_paths: set[str] = set()
        self.current_path = ""
        # Canonical name -> the name listing surfaces emit (bare for a precedence winner).
        self.listed: dict[str, str] = {}

    def _listed(self, name: str) -> str:
        return self.listed.get(name, name)

    def _resolve(self, name: str) -> str:
        """Accept a listed bare name as input, as lemond does, and return the canonical name."""
        if name in self.models:
            return name
        return next((canonical for canonical, bare in self.listed.items() if bare == name), name)

    def _refuse(self, message: str) -> tuple[int, Any]:
        return 500, {"error": {"message": message}}

    def _load(self, payload: dict[str, Any]) -> tuple[int, Any]:
        name = payload["model_name"]
        if name not in self.models:
            return 404, {"error": {"message": f"Model not found: {name}"}}
        fetches = self.auto_pull or self.current_path in self.auto_pull_paths
        if not self.models[name].get("downloaded") and not fetches:
            return self._refuse(f"Failed to load model: {name} is not downloaded")
        ctx = int(payload.get("ctx_size", 4096))
        predicted = 1.7 + ctx * 114688 / 2**30
        configured = self.config["max_gpu_memory_occupancy_gb"]
        capacity = self.capacity_gb if configured < 0 else min(configured, self.capacity_gb)
        if predicted > capacity:
            return self._refuse(
                f"Predicted GPU memory occupancy {predicted} GB for requested model "
                f"cannot fit within effective capacity {capacity} GB"
            )
        for resident, entry in list(self.loaded.items()):
            if resident == name:
                continue
            if entry["pinned"] or resident == self.busy_model:
                return self._refuse("All loaded models of type llm are pinned. Unload a model first.")
            del self.loaded[resident]
        self.next_pid += 1
        self.loaded[name] = {
            "model_name": name,
            "pid": self.next_pid,
            "pinned": name in self.config["pinned_models"],
            "is_busy": False,
            "recipe_options": {"llamacpp_backend": payload.get("llamacpp_backend", "rocm")},
        }
        return 200, {"status": "success"}

    def request(self, method: str, path: str, payload: Any = None, *, timeout=None, check=True):
        self.calls.append((method, path))
        status, body = self._dispatch(method, path, payload)
        message = live.error_message(body)
        if check and (status >= 400 or message):
            raise live.LemonadeError(f"{method} {path} -> {status}: {message}")
        return status, body

    def _dispatch(self, method: str, path: str, payload: Any) -> tuple[int, Any]:
        self.current_path = path
        if path == "/health":
            for name, entry in self.loaded.items():
                entry["is_busy"] = name == self.busy_model
            loaded = [{**entry, "model_name": self._listed(entry["model_name"])} for entry in self.loaded.values()]
            return 200, {"version": "11.7.0", "all_models_loaded": loaded}
        if path == "/models":
            return 200, {"data": list(self.models.values())}
        if path.startswith("/models/") and path.endswith("/files?include_paths=true"):
            return 200, {
                "files": [{"role": "main", "exists": True, "path": str(SERVICE_GGUF)}]
            }
        if path.startswith("/models/"):
            name = self._resolve(path.removeprefix("/models/"))
            if name not in self.models:
                return 404, {"error": {"message": f"Model not found: {name}"}}
            return 200, self.models[name]
        if path == "/load":
            return self._load(payload)
        if path == "/unload":
            self.loaded.pop(payload["model_name"], None)
            return 200, {"status": "success"}
        if path == "/pins" and method == "POST":
            self.config["pinned_models"].append(payload["model_name"])
            self.loaded[payload["model_name"]]["pinned"] = True
            return 200, {"status": "success"}
        if path == "/pins":
            return 200, {
                "data": [
                    {"model_name": self._listed(name), "loaded": name in self.loaded, "load_error": None}
                    for name in self.config["pinned_models"]
                ]
            }
        if path.startswith("/pins/") and method == "DELETE":
            name = path.removeprefix("/pins/")
            self.config["pinned_models"].remove(name)
            if name in self.loaded:
                self.loaded[name]["pinned"] = False
            return 200, {"status": "success"}
        if path == "/internal/set":
            self.config.update(payload)
            return 200, {"status": "success"}
        if path == "/internal/config":
            return 200, json.loads(json.dumps(self.config))
        if path == "/internal/shutdown":
            return 200, {}
        if path == "/system-info":
            return 200, {
                "model_storage": {"path": str(self.model_storage)},
                "devices": {
                    "amd_gpu": [
                        {
                            "name": "AMD Radeon 8060S",
                            "available": True,
                            "gpu_type": "integrated",
                            "family": "gfx1151",
                            "vram_gb": 0.5,
                            "virtual_mem_gb": 110.0,
                        }
                    ]
                },
                "recipes": {
                    "llamacpp": {
                        "backends": {"rocm": {"state": "installed", "devices": ["amd_gpu"]}}
                    }
                },
            }
        if path == "/completions":
            return 200, {"choices": [{"text": " Paris."}]}
        if path == "/chat/completions":
            # Inference auto-load: load a model that is not resident, then answer.
            name = payload["model"]
            if name not in self.loaded:
                status, body = self._load({"model_name": name, "ctx_size": payload.get("ctx_size", 4096)})
                if status >= 400:
                    return status, body
            return 200, {"choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]}
        if path == "/api/chat":
            # Ollama auto-load: lemond strips ":latest" and answers 404 on any load failure.
            name = payload["model"].removesuffix(":latest")
            if name not in self.loaded:
                ctx = (payload.get("options") or {}).get("num_ctx", 4096)
                status, _ = self._load({"model_name": name, "ctx_size": ctx})
                if status >= 400:
                    return 404, {"error": f"model '{name}' not found, try pulling it first"}
            return 200, {"model": name, "message": {"role": "assistant", "content": "OK"}, "done": True}
        raise AssertionError(f"unexpected request {method} {path}")

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)[1]

    def post(self, path: str, payload: Any, **kwargs):
        return self.request("POST", path, payload, **kwargs)[1]

    def stream_lines(self, path: str, payload: Any, *, timeout=None):
        self.busy_model = payload["model"]
        started_at = len(self.calls)
        yield 'data: {"choices": [{"text": " 4,"}]}'
        while ("POST", "/load") not in self.calls[started_at:]:
            time.sleep(0.001)
            yield ": keep-alive"
        yield 'data: {"choices": [{"text": " 5,"}]}'
        self.busy_model = None
        yield "data: [DONE]"


class FakeInstance:
    def __init__(self, server: FakeLemond) -> None:
        self.client = server
        self.restarts = 0

    def config_file(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.client.config))

    def restart(self) -> None:
        self.restarts += 1
        self.client.loaded.clear()
        for name in self.client.config["pinned_models"]:
            self.client._load({"model_name": name})

    def extra_model(self, stem: str) -> str:
        return f"extra.{stem}.gguf"


def test_text_mode_proves_packaged_backend_and_restores_residency(capsys: pytest.CaptureFixture[str]):
    server = FakeLemond(models=[MODEL])

    live.run_text(
        server,
        model=MODEL,
        backend="vulkan",
        ctx_size=4096,
        expect_checkpoint="Qwen/Qwen3-0.6B-GGUF:Q8_0",
        expect_sha256=PINNED_SHA256,
        owner_of=lambda path: "llama.cpp-vulkan-gfx1151",
        executable_of=lambda pid: "/opt/llama.cpp-vulkan-gfx1151/bin/llama-server",
        digest_of=lambda path: PINNED_SHA256 if path == SERVICE_GGUF else "other",
        libraries_of=lambda pid: {"/opt/llama.cpp-vulkan-gfx1151/lib/libggml-vulkan.so"},
        repo_packages_of=lambda repo: {"llama.cpp-vulkan-gfx1151"},
    )

    out = capsys.readouterr().out
    for marker in (
        "model_sha256_ok",
        "model_provisioned_ok",
        "backend_selected_ok",
        "backend_package_ok",
        "completion_ok",
        "backend_libraries_repo_owned_ok",
        "residency_restored",
    ):
        assert marker in out
    assert str(SERVICE_GGUF) not in out
    assert MODEL not in server.loaded


def test_text_mode_requires_the_pinned_checkpoint_and_digest():
    server = FakeLemond(models=[MODEL])

    with pytest.raises(AssertionError, match="not 'Qwen/Qwen3-0.6B-GGUF:Q4_0'"):
        live.run_text(
            server,
            model=MODEL,
            backend="rocm",
            ctx_size=4096,
            expect_checkpoint="Qwen/Qwen3-0.6B-GGUF:Q4_0",
        )
    with pytest.raises(AssertionError, match="model_sha256 mismatch"):
        live.run_text(
            server,
            model=MODEL,
            backend="rocm",
            ctx_size=4096,
            expect_checkpoint="Qwen/Qwen3-0.6B-GGUF:Q8_0",
            expect_sha256=PINNED_SHA256,
            digest_of=lambda path: "0" * 64,
        )
    assert ("POST", "/load") not in server.calls


def test_bound_gguf_digest_is_verified(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"gguf")
    digest = hashlib.sha256(b"gguf").hexdigest()

    verify_sha256(gguf, None)
    verify_sha256(gguf, digest.upper())
    assert "model_sha256_ok" in capsys.readouterr().out
    with pytest.raises(AssertionError, match="model_sha256 mismatch"):
        verify_sha256(gguf, "0" * 64)


def test_text_mode_rejects_bundled_backend_and_still_restores(capsys: pytest.CaptureFixture[str]):
    server = FakeLemond(models=[MODEL])

    with pytest.raises(AssertionError, match="not llama.cpp-hip-gfx1151"):
        live.run_text(
            server,
            model=MODEL,
            backend="rocm",
            ctx_size=4096,
            expect_checkpoint=None,
            owner_of=lambda path: "lemonade-managed",
            executable_of=lambda pid: "/var/lib/lemonade/bin/llama-server",
        )

    assert MODEL not in server.loaded
    assert "residency_restored" in capsys.readouterr().out


ROCM_LIBS = {
    "/opt/llama.cpp-hip-gfx1151/lib/libggml-hip.so": "llama.cpp-hip-gfx1151",
    "/opt/llama.cpp-hip-gfx1151/lib/libllama.so": "llama.cpp-hip-gfx1151",
    "/opt/rocm/lib/libamdhip64.so.7": "hip-runtime-amd-gfx1151",
    "/opt/rocm/lib/libhsa-runtime64.so.1": "hsa-rocr-gfx1151",
}
REPO_PACKAGES = {"llama.cpp-hip-gfx1151", "hip-runtime-amd-gfx1151", "hsa-rocr-gfx1151"}
LEMOND_CACHE_BIN = Path("/var/cache/lemond-test/bin")


def _owner_from(owners: dict[str, str]):
    def owner_of(path: str) -> str:
        if path not in owners:
            raise AssertionError(f"pacman -Qo {path} exited 1: error: No package owns {path}")
        return owners[path]

    return owner_of


def _verify_libs(owners: dict[str, str], *, paths=None, backend="rocm", repo_packages=REPO_PACKAGES):
    live.verify_backend_libraries(
        set(owners) if paths is None else set(paths),
        backend=backend,
        repo="strix-halo-gfx1151",
        repo_packages=repo_packages,
        cache_bins=(LEMOND_CACHE_BIN,),
        owner_of=_owner_from(owners),
    )


def test_mapped_libraries_selects_backend_objects_from_proc_maps(tmp_path: Path):
    maps = tmp_path / "proc" / "4001" / "maps"
    maps.parent.mkdir(parents=True)
    maps.write_text(
        "\n".join(
            [
                "7f00-7f10 r-xp 00000000 00:1f 11 /opt/llama.cpp-hip-gfx1151/lib/libggml-hip.so",
                "7f10-7f20 r--p 00010000 00:1f 11 /opt/llama.cpp-hip-gfx1151/lib/libggml-hip.so",
                "7f20-7f30 r-xp 00000000 00:1f 12 /opt/rocm/lib/libamdhip64.so.7.1.0",
                "7f30-7f40 r-xp 00000000 00:1f 13 /usr/lib/libc.so.6",
                "7f40-7f50 r-xp 00000000 00:1f 14 /var/cache/lemond-test/bin/rocm/libhsa-runtime64.so.1 (deleted)",
                "7f50-7f60 rw-p 00000000 00:00 0 [heap]",
                "7f60-7f70 rw-p 00000000 00:00 0",
            ]
        )
        + "\n"
    )

    assert live.mapped_libraries(4001, proc_root=tmp_path / "proc") == {
        "/opt/llama.cpp-hip-gfx1151/lib/libggml-hip.so",
        "/opt/rocm/lib/libamdhip64.so.7.1.0",
        "/var/cache/lemond-test/bin/rocm/libhsa-runtime64.so.1",
    }
    with pytest.raises(AssertionError, match="backend_maps_unreadable"):
        live.mapped_libraries(4002, proc_root=tmp_path / "proc")


def test_backend_libraries_must_come_from_repo_packages(capsys: pytest.CaptureFixture[str]):
    _verify_libs(ROCM_LIBS)

    out = capsys.readouterr().out
    assert "backend_libraries 4" in out
    assert "backend_libraries_from_cache 0" in out
    assert "backend_library_package llama.cpp-hip-gfx1151 2" in out
    assert "backend_library_package hip-runtime-amd-gfx1151 1" in out
    assert "backend_libraries_repo_owned_ok" in out
    assert "/opt/" not in out


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda owners: owners.update({f"{LEMOND_CACHE_BIN}/rocm/libhsa-runtime64.so.1": "x"}), "from lemond's cache bin"),
        (lambda owners: owners.update({"/opt/rocm/lib/libhsa-runtime64.so.1": "hsa-rocr"}), "outside strix-halo-gfx1151"),
        (lambda owners: owners.update({"/opt/llama.cpp-hip-gfx1151/lib/libllama.so": "hip-runtime-amd-gfx1151"}), "ggml/llama/mtmd libraries are owned by"),
    ],
)
def test_backend_libraries_reject_cache_unowned_foreign_or_missing_objects(mutate, message):
    owners = dict(ROCM_LIBS)
    mutate(owners)
    with pytest.raises(AssertionError, match=message):
        _verify_libs(owners)


def test_backend_libraries_reject_unowned_objects_and_a_missing_hip_runtime():
    owners = dict(ROCM_LIBS)
    del owners["/opt/rocm/lib/libhsa-runtime64.so.1"]
    with pytest.raises(AssertionError, match="1 backend libraries are not owned by any package"):
        _verify_libs(owners, paths=ROCM_LIBS)

    del owners["/opt/rocm/lib/libamdhip64.so.7"]
    with pytest.raises(AssertionError, match="no HIP runtime mapped"):
        _verify_libs(owners)


def test_backend_libraries_require_llamacpp_objects():
    with pytest.raises(AssertionError, match="no ggml, llama, or mtmd shared object"):
        _verify_libs({"/opt/rocm/lib/libamdhip64.so.7": "hip-runtime-amd-gfx1151"})


def test_text_mode_rejects_cached_therock_runtime_and_still_restores(capsys: pytest.CaptureFixture[str]):
    server = FakeLemond(models=[MODEL])
    libs = {**ROCM_LIBS, f"{LEMOND_CACHE_BIN}/therock/lib/libamdhip64.so.7": "unowned"}

    with pytest.raises(AssertionError, match="1 backend libraries load from lemond's cache bin"):
        live.run_text(
            server,
            model=MODEL,
            backend="rocm",
            ctx_size=4096,
            expect_checkpoint=None,
            cache_bins=(LEMOND_CACHE_BIN,),
            owner_of=lambda path: ROCM_LIBS.get(path, "llama.cpp-hip-gfx1151"),
            executable_of=lambda pid: "/opt/llama.cpp-hip-gfx1151/bin/llama-server",
            libraries_of=lambda pid: set(libs),
            repo_packages_of=lambda repo: REPO_PACKAGES,
        )

    out = capsys.readouterr().out
    assert "completion_ok" in out
    assert "residency_restored" in out
    assert str(LEMOND_CACHE_BIN) not in out
    assert MODEL not in server.loaded


def test_text_mode_refuses_unprovisioned_model_without_loading():
    server = FakeLemond(models=[MODEL])
    server.models[MODEL]["downloaded"] = False

    with pytest.raises(AssertionError, match="model_not_provisioned"):
        live.run_text(server, model=MODEL, backend="rocm", ctx_size=4096, expect_checkpoint=None)

    assert ("POST", "/load") not in server.calls


def test_lifecycle_pins_budget_and_displacement_flows(capsys: pytest.CaptureFixture[str]):
    live.run_lifecycle(FakeInstance(FakeLemond(models=[])), expect_family="gfx1151")
    live.run_pins(FakeInstance(FakeLemond(models=[EXTRA_A])), ctx_size=4096, timeout=1.0)
    live.run_budget(FakeInstance(FakeLemond(models=[EXTRA_A])), ctx_size=4096)
    live.run_displacement(
        FakeInstance(FakeLemond(models=[EXTRA_A, EXTRA_B])), ctx_size=4096, stream_tokens=64
    )

    out = capsys.readouterr().out
    for marker in (
        "hip_discovery_ok",
        "config_persisted_ok",
        "config_preserved_ok",
        "pin_persisted_ok",
        "pin_restored_ok",
        "pin_restored_pinned_ok",
        "pin_removed_ok",
        "apu_gtt_reported_ok",
        "budget_refuse_ok",
        "gtt_counted_ok",
        "budget_admit_ok",
        "configured_budget_refuse_ok",
        "pinned_not_displaced_ok",
        "busy_window_ok",
        "in_use_not_displaced_ok",
        "busy_request_completed_ok",
        "idle_displacement_control_ok",
    ):
        assert marker in out


def test_budget_fails_when_capacity_is_dedicated_vram_only():
    server = FakeLemond(models=[EXTRA_A], capacity_gb=0.5)

    with pytest.raises(AssertionError, match="does not exceed dedicated VRAM"):
        live.run_budget(FakeInstance(server), ctx_size=4096)


def test_displacement_fails_when_a_pinned_model_is_evicted():
    server = FakeLemond(models=[EXTRA_A, EXTRA_B])
    original_load = server._load

    def evicting_load(payload):
        for entry in server.loaded.values():
            entry["pinned"] = False
        return original_load(payload)

    server._load = evicting_load

    with pytest.raises(AssertionError, match="displaced the pinned model"):
        live.run_displacement(FakeInstance(server), ctx_size=4096, stream_tokens=64)


SECRETS = "/etc/lemonade/conf.d/zz-secrets.conf"
UNREADABLE = live.UNREADABLE_CHECKSUM


def _pacman_runner(
    *,
    packagers: dict[str, str] | None = None,
    foreign: str = "",
    alterations: dict[str, tuple[str, ...]] | None = None,
    backups: str = "None",
    counted: int | None = None,
):
    """Fake pacman; `alterations` and `backups` apply to lemonade-server only."""
    packagers = packagers or {}
    alterations = alterations or {}

    def runner(argv, capture_output, text):
        command = argv[:2]
        stdout = ""
        code = 0
        if command == ["pacman", "-Qi"]:
            package = argv[2]
            stdout = f"Name : {package}\nVersion : 1-1\nPackager : {packagers.get(package, 'Repo Builder')}\n"
        elif command == ["pacman", "-Si"]:
            package = argv[2].split("/", 1)[1]
            stdout = f"Repository : strix-halo-gfx1151\nName : {package}\nVersion : 1-1\nPackager : Repo Builder\n"
        elif command == ["pacman", "-Qmq"]:
            stdout, code = foreign, 0 if foreign else 1
        elif command == ["pacman", "-Qo"]:
            path = argv[2]
            owner = live.OWNED_PATHS.get(path)
            if owner is None:
                owner = "lemonade-server" if path.endswith("lemond") else (
                    "llama.cpp-hip-gfx1151" if "hip" in path else "llama.cpp-vulkan-gfx1151"
                )
            stdout = f"{path} is owned by {owner} 1-1\n"
        elif command == ["pacman", "-Qkk"]:
            package = argv[2]
            found = alterations if package == "lemonade-server" else {}
            count = len(found) if counted is None or package != "lemonade-server" else counted
            stdout = f"{package}: 10 total files, {count} altered files\n"
            stderr = "".join(
                f"warning: {package}: {path} ({reason})\n" for path, reasons in found.items() for reason in reasons
            )
            return subprocess.CompletedProcess(argv, 1 if count else 0, stdout=stdout, stderr=stderr)
        elif command == ["pacman", "-Qii"]:
            listed = backups if argv[2] == "lemonade-server" else "None"
            stdout = f"Name : {argv[2]}\nBackup Files : {listed}\nExtended Data : pkgtype=pkg\n"
        elif argv[0] == "systemctl":
            stdout = "4242\n"
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr="")

    return runner


def _provenance_server() -> FakeLemond:
    server = FakeLemond(models=[])
    server.config["llamacpp"] = {
        "rocm_bin": "/opt/llama.cpp-hip-gfx1151/bin",
        "vulkan_bin": "/usr/bin/llama-server-vulkan-gfx1151",
    }
    return server


def _run_provenance(server: FakeLemond, runner) -> None:
    live.run_provenance(
        server,
        repo="strix-halo-gfx1151",
        service="lemond.service",
        runner=runner,
        executable_of=lambda pid: "/usr/bin/lemond",
        path_is_dir=lambda path: str(path).endswith("/bin"),
    )


def test_provenance_accepts_uniform_repo_family(capsys: pytest.CaptureFixture[str]):
    _run_provenance(_provenance_server(), _pacman_runner())

    out = capsys.readouterr().out
    for marker in (
        "family_packager_uniform_ok",
        "no_foreign_package_ok",
        "service_executable_owned_ok",
        "package_files_unaltered_ok",
        "offline_config_ok",
        "no_bundled_backend_ok",
        "provenance_ok",
    ):
        assert marker in out


def test_provenance_records_an_unreadable_backup_file_without_counting_it(capsys: pytest.CaptureFixture[str]):
    runner = _pacman_runner(alterations={SECRETS: (UNREADABLE,)}, backups=f"{SECRETS} [unreadable]")

    _run_provenance(_provenance_server(), runner)

    out = capsys.readouterr().out
    assert "package_backup_unreadable lemonade-server etc/lemonade/conf.d/zz-secrets.conf" in out
    assert "package_files_unaltered_ok" in out


def test_provenance_counts_unverifiable_or_drifted_files_as_altered():
    # A checksum failure on a file pacman does not list as an unreadable backup still counts.
    for backups in ("None", f"{SECRETS} [unmodified]"):
        runner = _pacman_runner(alterations={SECRETS: (UNREADABLE,)}, backups=backups)
        with pytest.raises(AssertionError, match="zz-secrets.conf \\(failed to calculate"):
            _run_provenance(_provenance_server(), runner)

    # The M4 dry-run host: service-user-owned config dirs and a hand-edited resource.
    defaults = "/usr/share/lemonade-server/resources/architecture_defaults.json"
    runner = _pacman_runner(
        alterations={
            "/etc/lemonade": ("UID mismatch", "GID mismatch"),
            SECRETS: (UNREADABLE,),
            defaults: ("Modification time mismatch", "Size mismatch", "SHA256 checksum mismatch"),
        },
        backups=f"{SECRETS} [unreadable]",
    )
    with pytest.raises(AssertionError) as caught:
        _run_provenance(_provenance_server(), runner)
    # Package-archive paths survive the scrubbed one-line error report.
    message = live.scrub_paths(str(caught.value))
    assert "etc/lemonade (GID mismatch, UID mismatch)" in message
    assert "usr/share/lemonade-server/resources/architecture_defaults.json (Modification time" in message
    assert "<path>" not in message
    assert "zz-secrets" not in message

    # A count that the named paths do not account for fails closed.
    runner = _pacman_runner(alterations={"/usr/bin/lemond": ("Size mismatch",)}, counted=2)
    with pytest.raises(AssertionError, match="counts 2 altered files but names 1"):
        _run_provenance(_provenance_server(), runner)


def test_provenance_rejects_mixed_foreign_altered_or_online_family():
    with pytest.raises(AssertionError, match="packager differs"):
        _run_provenance(_provenance_server(), _pacman_runner(packagers={"lemonade-app": "Other"}))
    with pytest.raises(AssertionError, match="foreign"):
        _run_provenance(_provenance_server(), _pacman_runner(foreign="lemonade-server\n"))
    with pytest.raises(AssertionError, match="altered"):
        _run_provenance(
            _provenance_server(),
            _pacman_runner(alterations={"/usr/bin/lemond": ("SHA256 checksum mismatch",)}),
        )

    online = _provenance_server()
    online.config["offline"] = False
    with pytest.raises(AssertionError, match="offline"):
        _run_provenance(online, _pacman_runner())

    bundled = _provenance_server()
    bundled.config["llamacpp"]["rocm_bin"] = "builtin"
    with pytest.raises(AssertionError, match="bundled backend"):
        _run_provenance(bundled, _pacman_runner())


# --- No-fetch evidence and consumer pins -------------------------------------

LEMOND_PID = 4000
LLAMA_PID = 4001
BLACKHOLE_ENV = "HF_ENDPOINT=http://127.0.0.1:9 MODELSCOPE_ENDPOINT=http://[::1]:9"


def _listen_row(pid: int = LEMOND_PID) -> str:
    return f'LISTEN 0 512 0.0.0.0:13305 0.0.0.0:* users:(("lemond",pid={pid},fd=7))'


class FakeHost(live.ServiceHost):
    """ServiceHost over a fake runner and /proc tree; journal lines are injected."""

    def __init__(self, tmp_path: Path, *, environment: str = BLACKHOLE_ENV) -> None:
        self.proc = tmp_path / "proc"
        (self.proc / str(LEMOND_PID) / "task" / str(LEMOND_PID)).mkdir(parents=True)
        (self.proc / str(LEMOND_PID) / "task" / str(LEMOND_PID) / "children").write_text(f"{LLAMA_PID}\n")
        (self.proc / str(LEMOND_PID) / "cmdline").write_bytes(b"/usr/bin/lemond\0")
        self.environment = environment
        self.user_home = tmp_path / "home"
        self.ss_rows = [_listen_row()]
        self.journal: list[str] = []
        self.commands: list[list[str]] = []
        super().__init__("lemond.service", runner=self._run, proc_root=self.proc)

    def _run(self, argv, **kwargs):
        self.commands.append(argv)
        if argv[:2] == ["systemctl", "show"]:
            values = {"MainPID": str(LEMOND_PID), "Environment": self.environment, "User": "lemonade"}
            stdout = values[argv[3]] + "\n"
        elif argv[0] == "ss":
            stdout = "\n".join(self.ss_rows) + "\n"
        elif argv[0] == "journalctl":
            # Entry i has cursor "c<i>"; this mirrors journalctl -n 1 and --after-cursor.
            entries = list(enumerate(self.journal))
            if "-n" in argv:
                entries = entries[-int(argv[argv.index("-n") + 1]):] if entries else []
            if "--after-cursor" in argv:
                after = int(argv[argv.index("--after-cursor") + 1].removeprefix("c"))
                entries = entries[after + 1:]
            stdout = "".join(json.dumps({"__CURSOR": f"c{i}", "MESSAGE": line}) + "\n" for i, line in entries)
        else:
            raise AssertionError(f"unexpected command {argv}")
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def cache_dir(self) -> Path:
        return self.user_home / ".cache" / "lemonade"


def _nofetch_setup(tmp_path: Path):
    server = FakeLemond(models=[MODEL, "Tiny-Test-Model-GGUF"])
    server.models["Tiny-Test-Model-GGUF"]["downloaded"] = False
    server.model_storage = tmp_path / "hf-cache"
    (server.model_storage / "models--Qwen--Qwen3-0.6B-GGUF" / "blobs").mkdir(parents=True)
    (server.model_storage / "models--Qwen--Qwen3-0.6B-GGUF" / "blobs" / "abc").write_bytes(b"gguf")
    host = FakeHost(tmp_path)
    (host.cache_dir() / "bin").mkdir(parents=True)
    return server, host


def _fake_text(host: FakeHost, *, journal=(), ss_rows=(), touch: Path | None = None):
    def text(client, **kwargs):
        host.journal += [f"Ensuring model loaded: {kwargs['model']}", *journal]
        host.ss_rows += list(ss_rows)
        if touch is not None:
            touch.write_text("x", encoding="utf-8")
        print("completion_ok")

    return text


def _run_nofetch(server, host, **kwargs):
    original = server._load

    def logged_load(payload):
        host.journal.append(f"Ensuring model loaded: {payload['model_name']}")
        return original(payload)

    server._load = logged_load
    live.run_nofetch(
        server,
        host=host,
        model=MODEL,
        missing_model=kwargs.pop("missing_model", "Tiny-Test-Model-GGUF"),
        backend="rocm",
        ctx_size=4096,
        expect_checkpoint=None,
        expect_sha256=None,
        interval=0.01,
        journal_settle=kwargs.pop("journal_settle", 0.0),
        text=kwargs.pop("text", _fake_text(host)),
    )


AUTO_PULL_ROUTES = {"load": "/load", "inference": "/chat/completions", "ollama": "/api/chat"}
PHASES = [f"{kind}_{path}" for kind in ("preplaced", "missing") for path in AUTO_PULL_ROUTES]


def _evidence_on(server, host, *, route: str, model: str, journal=(), ss_rows=(), touch: Path | None = None, reply=None):
    """When `route` names `model`, add fetch evidence or replace the reply."""
    original = server._dispatch

    def dispatch(method, path, payload):
        named = (payload or {}).get("model_name") or (payload or {}).get("model") or ""
        if method == "POST" and path == route and named.removesuffix(":latest") == model:
            host.journal += list(journal)
            host.ss_rows += list(ss_rows)
            if touch is not None:
                touch.write_text("x", encoding="utf-8")
            if reply is not None:
                return reply
        return original(method, path, payload)

    server._dispatch = dispatch


def _touch_target(server, host, kind: str | None, name: str) -> Path | None:
    if kind == "model":
        return server.model_storage / "models--Qwen--Qwen3-0.6B-GGUF" / "blobs" / name
    if kind == "backend":
        return host.cache_dir() / "bin" / "llama-server"
    return None


def test_ss_parsing_and_loopback_detection():
    rows = live.parse_ss(
        "\n".join(
            [
                _listen_row(),
                'ESTAB 0 0 127.0.0.1:41000 127.0.0.1:8001 users:(("lemond",pid=4000,fd=9))',
                'SYN-SENT 0 1 198.51.100.5:50000 [2600:1f18::1]:443 users:(("llama-server",pid=4001,fd=3))',
                "ESTAB 0 0 [::ffff:127.0.0.1]:13305 [::ffff:127.0.0.1]:5000",
                "ESTAB 0 0 127.0.0.53%lo:53 127.0.0.53%lo:40000",
            ]
        )
    )

    assert [row["state"] for row in rows] == ["LISTEN", "ESTAB", "SYN-SENT", "ESTAB", "ESTAB"]
    assert rows[1]["pids"] == {LEMOND_PID}
    assert (rows[2]["peer_host"], rows[2]["peer_port"], rows[2]["pids"]) == ("2600:1f18::1", "443", {LLAMA_PID})
    assert rows[3]["pids"] == set()
    for row, loopback in zip(rows[1:], (True, False, True, True)):
        assert live.is_loopback_host(row["peer_host"]) is loopback
    assert live.is_loopback_host("localhost")
    assert not live.is_loopback_host("huggingface.co")


def test_blackhole_ports_require_loopback_endpoints():
    assert live.blackhole_ports(
        {"HF_ENDPOINT": "http://127.0.0.1:9", "MODELSCOPE_ENDPOINT": "https://localhost"}
    ) == {"9", "443"}
    for env in (
        {"HF_ENDPOINT": "http://127.0.0.1:9"},
        {"HF_ENDPOINT": "https://huggingface.co", "MODELSCOPE_ENDPOINT": "http://127.0.0.1:9"},
    ):
        with pytest.raises(AssertionError, match="endpoint_blackhole_missing"):
            live.blackhole_ports(env)


def test_fetch_log_pattern_matches_fetches_but_not_cache_state():
    fetches = [
        "Model not downloaded, downloading...",
        "Model not cached, downloading from Hugging Face...",
        "Downloading model: unsloth/gemma-3-270m-it-GGUF",
        "Downloaded: model.gguf",
        "Fetching repository file list from Hugging Face",
        "Installing llama-server (version: b1234)",
        "TheRock installation complete",
    ]
    quiet = [
        "Added 'x' to cache (downloaded=1)",
        "Model already downloaded and do_not_upgrade=true, using cached version",
        "Uninstalling llamacpp:rocm",
        "Ensuring model loaded: user.Qwen3-0.6B-Q8_0-GGUF",
    ]
    assert all(live.FETCH_LOG_RE.search(line) for line in fetches)
    assert not any(live.FETCH_LOG_RE.search(line) for line in quiet)


def test_snapshot_tree_detects_new_resized_and_relinked_entries(tmp_path: Path):
    root = tmp_path / "cache"
    (root / "snapshots").mkdir(parents=True)
    (root / "blob").write_bytes(b"a")
    (root / "snapshots" / "model.gguf").symlink_to(root / "blob")
    before = live.snapshot_tree(root)

    assert live.tree_changes(before, live.snapshot_tree(root)) == []
    (root / "blob.incomplete").write_bytes(b"")
    (root / "snapshots" / "model.gguf").unlink()
    (root / "snapshots" / "model.gguf").symlink_to(root / "blob.incomplete")
    assert live.tree_changes(before, live.snapshot_tree(root)) == ["blob.incomplete", "snapshots/model.gguf"]
    assert live.snapshot_tree(tmp_path / "absent") == {}


def test_service_host_reads_only_blackhole_env_and_filters_journal(tmp_path: Path):
    host = FakeHost(tmp_path, environment="LEMONADE_API_KEY=secret")
    (host.proc / str(LEMOND_PID) / "environ").write_bytes(
        b"LEMONADE_API_KEY=secret\0HF_ENDPOINT=http://127.0.0.1:9\0MODELSCOPE_ENDPOINT=http://127.0.0.1:9\0"
    )

    assert host.endpoint_env() == {
        "HF_ENDPOINT": "http://127.0.0.1:9",
        "MODELSCOPE_ENDPOINT": "http://127.0.0.1:9",
    }
    assert host.process_tree(LEMOND_PID) == {LEMOND_PID, LLAMA_PID}
    assert host.journal_cursor() is None
    assert host.journal_after(None) == ([], None)
    host.journal = ["Ensuring model loaded: m", "second"]
    assert host.journal_cursor() == "c1"
    assert host.journal_after(None) == (["Ensuring model loaded: m", "second"], "c1")
    assert host.journal_after("c0") == (["second"], "c1")
    assert host.journal_after("c1") == ([], "c1")
    journal_argv = next(argv for argv in host.commands if argv[0] == "journalctl")
    assert journal_argv[:3] == ["journalctl", "-u", "lemond.service"]
    assert ["-o", "json"] == journal_argv[journal_argv.index("-o"):journal_argv.index("-o") + 2]


def test_service_host_cache_dir_prefers_argv_then_env(tmp_path: Path):
    host = FakeHost(tmp_path, environment="LEMONADE_CACHE_DIR=/srv/lemonade-cache")
    assert live.ServiceHost.cache_dir(host) == Path("/srv/lemonade-cache")
    (host.proc / str(LEMOND_PID) / "cmdline").write_bytes(b"/usr/bin/lemond\0/srv/other\0--port\0" + b"13305\0")
    assert live.ServiceHost.cache_dir(host) == Path("/srv/other")
    (host.proc / str(LEMOND_PID) / "cmdline").write_bytes(b"/usr/bin/lemond\0--port\0" + b"13305\0")
    assert live.ServiceHost.cache_dir(host) == Path("/srv/lemonade-cache")


def test_nofetch_proves_no_download_log_cache_change_or_remote_connection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    server, host = _nofetch_setup(tmp_path)
    host.ss_rows.append('ESTAB 0 0 127.0.0.1:41000 127.0.0.1:8001 users:(("lemond",pid=4000,fd=9))')

    _run_nofetch(server, host)

    out = capsys.readouterr().out
    markers = [
        "offline_config_ok",
        "endpoint_blackhole_ok",
        "network_attribution_ok",
        "missing_model_registered_ok",
        "missing_model_absent_ok",
        "completion_ok",
        "preplaced_inference_autoload_ok",
        "preplaced_ollama_autoload_ok",
        "missing_load_refused_ok",
        "missing_inference_refused_ok",
        "missing_ollama_refused_ok",
        "no_fetch_ok",
    ]
    for phase in PHASES:
        markers += [
            f"{phase}_no_fetch_log_ok",
            f"{phase}_model_cache_unchanged_ok",
            f"{phase}_backend_cache_unchanged_ok",
            f"{phase}_no_remote_connection_ok",
        ]
    for marker in markers:
        assert marker in out
    assert "blackholed_fetch_attempt_recorded" not in out
    assert str(tmp_path) not in out
    for route in AUTO_PULL_ROUTES.values():
        assert ("POST", route) in server.calls
    assert "Tiny-Test-Model-GGUF" not in server.loaded
    assert MODEL not in server.loaded


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"journal": ["Model not downloaded, downloading..."]}, "download or install lines"),
        ({"ss_rows": ['SYN-SENT 0 1 198.51.100.2:5000 203.0.113.9:443 users:(("lemond",pid=4000,fd=12))']}, "non-loopback"),
        ({"ss_rows": ['SYN-SENT 0 1 127.0.0.1:5000 127.0.0.1:9 users:(("lemond",pid=4001,fd=12))']}, "blackhole"),
        ({"touch": "model"}, "model_cache changed"),
        ({"touch": "backend"}, "backend_cache changed"),
    ],
)
def test_nofetch_fails_on_each_kind_of_fetch_evidence(tmp_path: Path, change: dict, message: str):
    server, host = _nofetch_setup(tmp_path)
    change = dict(change)
    touch = _touch_target(server, host, change.pop("touch", None), "new.incomplete")
    if touch is not None:
        change["touch"] = touch

    with pytest.raises(AssertionError, match=f"preplaced_load: .*{message}"):
        _run_nofetch(server, host, text=_fake_text(host, **change))


@pytest.mark.parametrize("path", ["inference", "ollama"])
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"journal": ["Model not cached, downloading from Hugging Face..."]}, "download or install lines"),
        ({"ss_rows": ['SYN-SENT 0 1 198.51.100.2:5000 203.0.113.9:443 users:(("lemond",pid=4000,fd=12))']}, "non-loopback"),
        ({"ss_rows": ['SYN-SENT 0 1 127.0.0.1:5000 127.0.0.1:9 users:(("lemond",pid=4000,fd=12))']}, "blackhole"),
        ({"touch": "model"}, "model_cache changed"),
        ({"touch": "backend"}, "backend_cache changed"),
    ],
)
def test_nofetch_preplaced_auto_load_paths_keep_the_strict_check(
    tmp_path: Path, path: str, change: dict, message: str
):
    server, host = _nofetch_setup(tmp_path)
    change = dict(change)
    touch = _touch_target(server, host, change.pop("touch", None), "auto.incomplete")
    _evidence_on(server, host, route=AUTO_PULL_ROUTES[path], model=MODEL, touch=touch, **change)

    with pytest.raises(AssertionError, match=f"preplaced_{path}: .*{message}"):
        _run_nofetch(server, host)
    assert MODEL not in server.loaded


@pytest.mark.parametrize("path", ["inference", "ollama"])
def test_nofetch_preplaced_auto_load_must_load_the_model(tmp_path: Path, path: str):
    server, host = _nofetch_setup(tmp_path)
    reply = (500, {"error": {"message": f"cannot open {server.model_storage}/models--Qwen/blobs/abc"}})
    _evidence_on(
        server, host, route=AUTO_PULL_ROUTES[path], model=MODEL, journal=[f"Auto-loading model: {MODEL}"], reply=reply
    )

    with pytest.raises(AssertionError, match=f"preplaced_{path}: auto-load of .* failed") as excinfo:
        _run_nofetch(server, host)
    assert str(tmp_path) not in str(excinfo.value)
    assert "<model_cache>" in str(excinfo.value)


def test_nofetch_unloads_a_resident_preplaced_model_and_restores_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    server, host = _nofetch_setup(tmp_path)
    server.loaded[MODEL] = {
        "model_name": MODEL,
        "pid": 50,
        "pinned": False,
        "is_busy": False,
        "recipe_options": {"llamacpp_backend": "vulkan", "ctx_size": 8192},
    }

    _run_nofetch(server, host)

    out = capsys.readouterr().out
    assert "preplaced_residency_restored" in out
    assert server.loaded[MODEL]["recipe_options"]["llamacpp_backend"] == "vulkan"
    # The missing phases run first; the model is unloaded before the pre-placed phases.
    completions = [i for i, call in enumerate(server.calls) if call == ("POST", "/chat/completions")]
    assert completions[0] < server.calls.index(("POST", "/unload")) < completions[-1]


def _resident_model_that_cannot_be_restored(server) -> None:
    server.loaded[MODEL] = {
        "model_name": MODEL,
        "pid": 50,
        "pinned": False,
        "is_busy": False,
        "recipe_options": {"llamacpp_backend": "vulkan", "ctx_size": 8192},
    }
    original = server._dispatch

    def dispatch(method, path, payload):
        if method == "POST" and path == "/load" and (payload or {}).get("llamacpp_backend") == "vulkan":
            return 500, {"error": {"message": "restore refused"}}
        return original(method, path, payload)

    server._dispatch = dispatch


def test_nofetch_restore_failure_does_not_mask_a_phase_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    server, host = _nofetch_setup(tmp_path)
    _resident_model_that_cannot_be_restored(server)
    _evidence_on(server, host, route="/chat/completions", model=MODEL, journal=["Downloading model: x"])

    with pytest.raises(AssertionError, match="preplaced_inference: the service logged 1 download"):
        _run_nofetch(server, host)
    out = capsys.readouterr().out
    assert f"preplaced_residency_restore_failed: {MODEL} was resident" in out
    assert "preplaced_residency_restored" not in out


def test_nofetch_restore_failure_fails_when_the_phases_passed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    server, host = _nofetch_setup(tmp_path)
    _resident_model_that_cannot_be_restored(server)

    with pytest.raises(AssertionError, match=f"{MODEL} was resident before the scenario and could not be restored"):
        _run_nofetch(server, host)
    assert "preplaced_ollama_no_remote_connection_ok" in capsys.readouterr().out


def _restore_request_raises(server, exc: BaseException, *, on: tuple[str, str]) -> None:
    """Make one request of the residency restore (its /load, or the /health after it) raise."""
    original = server.request
    restoring = False

    def request(method, path, payload=None, **kwargs):
        nonlocal restoring
        if (method, path) == ("POST", "/load") and (payload or {}).get("llamacpp_backend") == "vulkan":
            restoring = True
        if restoring and (method, path) == on:
            raise exc
        return original(method, path, payload, **kwargs)

    server.request = request


@pytest.mark.parametrize(
    ("exc", "on"),
    [
        (live.error.URLError(ConnectionRefusedError(111, "Connection refused")), ("POST", "/load")),
        (ConnectionResetError(104, "Connection reset by peer"), ("POST", "/load")),
        (live.LemonadeError("GET /health -> 503: restarting"), ("GET", "/health")),
    ],
)
def test_nofetch_restore_errors_do_not_mask_a_phase_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], exc: BaseException, on: tuple[str, str]
):
    server, host = _nofetch_setup(tmp_path)
    server.loaded[MODEL] = {
        "model_name": MODEL, "pid": 50, "pinned": False, "is_busy": False,
        "recipe_options": {"llamacpp_backend": "vulkan", "ctx_size": 8192},
    }
    _restore_request_raises(server, exc, on=on)
    _evidence_on(server, host, route="/chat/completions", model=MODEL, journal=["Downloading model: x"])

    with pytest.raises(AssertionError, match="preplaced_inference: the service logged 1 download"):
        _run_nofetch(server, host)
    assert f"preplaced_residency_restore_failed: {MODEL} was resident" in capsys.readouterr().out


def test_nofetch_restore_errors_fail_when_the_phases_passed(tmp_path: Path):
    server, host = _nofetch_setup(tmp_path)
    server.loaded[MODEL] = {
        "model_name": MODEL, "pid": 50, "pinned": False, "is_busy": False,
        "recipe_options": {"llamacpp_backend": "vulkan", "ctx_size": 8192},
    }
    _restore_request_raises(server, live.error.URLError("Connection refused"), on=("POST", "/load"))

    with pytest.raises(AssertionError, match=f"{MODEL} was resident .* could not be restored: .*Connection refused"):
        _run_nofetch(server, host)


def _watch(host: FakeHost, tmp_path: Path, **kwargs) -> live.FetchWatch:
    return live.FetchWatch(
        host, caches={"model_cache": tmp_path / "cache"}, blackhole={"9"},
        interval=0.01, journal_timeout=1.0, settle=0.0, **kwargs,
    )


def test_fetch_watch_windows_exclude_lines_from_before_the_phase(tmp_path: Path):
    host = FakeHost(tmp_path)
    host.journal = ["Downloading model: earlier phase"]
    with _watch(host, tmp_path, expect_log="m") as phase:
        host.journal.append("Ensuring model loaded: m")
    assert phase.journal == ["Ensuring model loaded: m"]
    assert (phase.start_cursor, phase.end_cursor) == ("c0", "c1")


def test_fetch_watch_windows_are_contiguous(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    host = FakeHost(tmp_path)
    with _watch(host, tmp_path, expect_log="m") as first:
        host.journal.append("Ensuring model loaded: m")
    first.verify("missing_ollama", record_blackholed_attempt=True)
    # A download line that lands after the first window closed belongs to the
    # next window, which starts at the first one's end cursor.
    host.journal.append("Model not cached, downloading from Hugging Face...")
    with _watch(host, tmp_path, expect_log="p", start_cursor=first.end_cursor) as second:
        host.journal.append("Ensuring model loaded: p")
    assert second.start_cursor == first.end_cursor == "c0"
    assert second.journal == ["Model not cached, downloading from Hugging Face...", "Ensuring model loaded: p"]
    with pytest.raises(AssertionError, match="preplaced_load: the service logged 1 download"):
        second.verify("preplaced_load")
    out = capsys.readouterr().out
    assert "missing_ollama_no_fetch_log_ok" in out
    assert "missing_ollama_blackholed_fetch_attempt_recorded" not in out


def test_fetch_watch_prints_either_the_clean_or_the_recorded_marker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    host = FakeHost(tmp_path)
    with _watch(host, tmp_path, expect_log="m") as phase:
        host.journal.append("Ensuring model loaded: m")
        host.ss_rows.append(BLACKHOLE_CONNECT)
    phase.verify("missing_load", record_blackholed_attempt=True)
    out = capsys.readouterr().out
    assert "missing_load_blackholed_fetch_attempt_recorded log_lines=0 blackhole_connects=" in out
    assert "missing_load_no_fetch_log_ok" not in out


@pytest.mark.parametrize(("settle", "collected"), [(0.3, True), (0.0, False)])
def test_fetch_watch_waits_for_the_journal_to_settle(tmp_path: Path, settle: float, collected: bool):
    host = FakeHost(tmp_path)
    reads = 0
    original = host.journal_after

    def journal_after(cursor):
        nonlocal reads
        reads += 1
        if reads == 2:  # journald flushes the download line one poll after the phase's own line.
            host.journal.append("Downloading model: m")
        return original(cursor)

    with _watch(host, tmp_path, expect_log="m") as phase:
        host.journal.append("Ensuring model loaded: m")
        phase.settle = settle
        host.journal_after = journal_after
    # Read 1 returns the phase's own line; only the settle wait makes read 2.
    assert ("Downloading model: m" in phase.journal) is collected


def test_nofetch_phase_windows_are_contiguous_and_charge_each_line_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    server, host = _nofetch_setup(tmp_path)
    watches: list = []
    enter = live.FetchWatch.__enter__

    def record_enter(self):
        watches.append(self)
        return enter(self)

    monkeypatch.setattr(live.FetchWatch, "__enter__", record_enter)
    _run_nofetch(server, host, journal_settle=0.01)
    # The missing phases run first; only the last missing and the last pre-placed window settle.
    assert [w.expect_log for w in watches] == ["Tiny-Test-Model-GGUF"] * 3 + [MODEL] * 3
    assert [w.settle > 0 for w in watches] == [False, False, True, False, False, True]
    for previous, current in zip(watches, watches[1:]):
        assert current.start_cursor == previous.end_cursor
    assert [line for w in watches for line in w.journal] == host.journal


def test_nofetch_late_missing_attempt_fails_in_the_strict_window(tmp_path: Path):
    server, host = _nofetch_setup(tmp_path)
    original = server._dispatch
    state = {"ollama": False, "late": False}

    def dispatch(method, path, payload):
        if (method, path) == ("POST", "/api/chat") and "Tiny" in (payload or {}).get("model", ""):
            state["ollama"] = True
        elif (method, path) == ("GET", "/health") and state["ollama"] and not state["late"]:
            # The last missing attempt is logged only after its window closed.
            state["late"] = True
            host.journal.append("Model not cached, downloading from Hugging Face...")
        return original(method, path, payload)

    server._dispatch = dispatch
    with pytest.raises(AssertionError, match="preplaced_load: the service logged 1 download"):
        _run_nofetch(server, host)


def test_missing_model_defaults_to_the_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(live.MISSING_MODEL_ENV, raising=False)
    assert live.parse_args(["nofetch"]).missing_model == live.DEFAULT_MISSING_MODEL
    monkeypatch.setenv(live.MISSING_MODEL_ENV, "Other-Absent-GGUF")
    assert live.parse_args(["nofetch"]).missing_model == "Other-Absent-GGUF"
    assert live.parse_args(["nofetch", "--missing-model", "Cli-GGUF"]).missing_model == "Cli-GGUF"


def test_nofetch_ignores_other_processes_and_inbound_lan_clients(tmp_path: Path):
    server, host = _nofetch_setup(tmp_path)
    other = 'ESTAB 0 0 198.51.100.2:5000 203.0.113.9:443 users:(("firefox",pid=77,fd=12))'
    inbound = 'ESTAB 0 0 198.51.100.2:13305 198.51.100.7:52000 users:(("lemond",pid=4000,fd=14))'

    _run_nofetch(server, host, text=_fake_text(host, ss_rows=[other, inbound]))


def test_nofetch_missing_model_must_be_registered_and_absent(tmp_path: Path):
    server, host = _nofetch_setup(tmp_path)
    with pytest.raises(AssertionError, match="missing_model_unregistered"):
        _run_nofetch(server, host, missing_model="user.never-registered")
    assert ("POST", "/load") not in server.calls

    server, host = _nofetch_setup(tmp_path / "second")
    server.models["Tiny-Test-Model-GGUF"]["downloaded"] = True
    with pytest.raises(AssertionError, match=f"missing_model_present: .*{live.MISSING_MODEL_ENV}"):
        _run_nofetch(server, host)
    assert ("POST", "/load") not in server.calls

    server, host = _nofetch_setup(tmp_path / "third")
    del server.models["Tiny-Test-Model-GGUF"]["downloaded"]
    with pytest.raises(AssertionError, match="missing_model_present: .*downloaded=None"):
        _run_nofetch(server, host)


@pytest.mark.parametrize("path", list(AUTO_PULL_ROUTES))
def test_nofetch_missing_model_must_fail_loudly_on_each_path(tmp_path: Path, path: str):
    server, host = _nofetch_setup(tmp_path)
    server.auto_pull_paths = {AUTO_PULL_ROUTES[path]}

    with pytest.raises(AssertionError, match=f"missing_{path}: Tiny-Test-Model-GGUF was admitted; it was fetched"):
        _run_nofetch(server, host)
    assert "Tiny-Test-Model-GGUF" not in server.loaded


BLACKHOLE_CONNECT = 'SYN-SENT 0 1 127.0.0.1:5000 127.0.0.1:9 users:(("lemond",pid=4000,fd=12))'


def _attempt_on_missing(server, host, *, paths=tuple(AUTO_PULL_ROUTES), **evidence):
    """Make the refused missing-model requests log and blackhole a download attempt."""
    for path in paths:
        _evidence_on(
            server, host, route=AUTO_PULL_ROUTES[path], model="Tiny-Test-Model-GGUF",
            journal=["Model not cached, downloading from Hugging Face..."], **evidence,
        )


def test_nofetch_records_a_blackholed_attempt_on_each_missing_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    server, host = _nofetch_setup(tmp_path)
    _attempt_on_missing(server, host, ss_rows=[BLACKHOLE_CONNECT])
    original = server._dispatch

    def dispatch(method, path, payload):
        if (method, path) == ("GET", "/health"):
            # A refused connect to the blackhole is gone once its phase's window has closed.
            host.ss_rows = [row for row in host.ss_rows if row != BLACKHOLE_CONNECT]
        return original(method, path, payload)

    server._dispatch = dispatch
    _run_nofetch(server, host)

    out = capsys.readouterr().out
    assert "preplaced_load_no_fetch_log_ok" in out
    for path in AUTO_PULL_ROUTES:
        phase = f"missing_{path}"
        assert f"{phase}_refused_ok" in out
        assert f"{phase}_fetch_log_lines 1" in out
        assert f"{phase}_no_fetch_log_ok" not in out
        assert f"{phase}_blackholed_fetch_attempt_recorded log_lines=1 blackhole_connects=" in out
        assert f"{phase}_model_cache_unchanged_ok" in out
        assert f"{phase}_no_remote_connection_ok" in out
    assert "no_fetch_ok" in out


def test_nofetch_missing_refusals_are_printed_without_host_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    server, host = _nofetch_setup(tmp_path)
    refusal = f"Failed to download into {host.cache_dir()}/bin and {server.model_storage}/models--unsloth"
    _evidence_on(
        server, host, route="/load", model="Tiny-Test-Model-GGUF",
        journal=["Ensuring model loaded: Tiny-Test-Model-GGUF"], reply=(500, {"error": {"message": refusal}}),
    )

    _run_nofetch(server, host)

    out = capsys.readouterr().out
    assert "missing_load_refusal" in out
    assert "<backend_cache>" in out and "<model_cache>" in out
    assert str(tmp_path) not in out


@pytest.mark.parametrize("path", list(AUTO_PULL_ROUTES))
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"ss_rows": ['SYN-SENT 0 1 198.51.100.2:5000 203.0.113.9:443 users:(("lemond",pid=4000,fd=12))']}, "lemond connected to 1 non-loopback"),
        ({"touch": "model"}, "model_cache changed"),
        ({"touch": "backend"}, "backend_cache changed"),
    ],
)
def test_nofetch_missing_model_attempt_fails_on_remote_or_cache_evidence(
    tmp_path: Path, path: str, change: dict, message: str
):
    server, host = _nofetch_setup(tmp_path)
    change = dict(change)
    touch = _touch_target(server, host, change.pop("touch", None), "tiny.incomplete")
    _attempt_on_missing(server, host, paths=(path,), touch=touch, **change)

    with pytest.raises(AssertionError, match=f"missing_{path}: {message}"):
        _run_nofetch(server, host)


def test_nofetch_preconditions_block_before_any_load(tmp_path: Path):
    server, host = _nofetch_setup(tmp_path)
    host.environment = ""
    with pytest.raises(AssertionError, match="endpoint_blackhole_missing"):
        _run_nofetch(server, host)

    server, host = _nofetch_setup(tmp_path / "second")
    host.ss_rows = ['LISTEN 0 512 0.0.0.0:13305 0.0.0.0:*']
    with pytest.raises(AssertionError, match="network_attribution_unavailable"):
        _run_nofetch(server, host)

    server, host = _nofetch_setup(tmp_path / "third")
    server.config["offline"] = False
    with pytest.raises(AssertionError, match="offline"):
        _run_nofetch(server, host)
    assert ("POST", "/load") not in server.calls


def _pinned_server() -> FakeLemond:
    zembed, zerank = "user.zembed-1-Q4_K_M-GGUF-Q4_K_M", "zerank-2-GGUF"
    server = FakeLemond(models=[zembed, zerank])
    server.models[zembed]["checkpoint"] = "example/zembed-1-Q4_K_M-GGUF:zembed-1-q4_k_m.gguf"
    server.models[zerank]["checkpoint"] = "mradermacher/zerank-2-GGUF:Q8_0"
    for pid, name in enumerate((zembed, zerank), start=200):
        server.config["pinned_models"].append(name)
        server.loaded[name] = {"model_name": name, "pid": pid, "pinned": True, "is_busy": False}
    return server


PINS = [("user.zembed-1-Q4_K_M-GGUF-Q4_K_M", "Q4_K_M"), ("zerank-2-GGUF", "Q8_0")]


def test_service_pins_accepts_pinned_loaded_consumer_models(capsys: pytest.CaptureFixture[str]):
    server = _pinned_server()

    live.run_service_pins(server, expected=PINS)

    out = capsys.readouterr().out
    assert "service_pin user.zembed-1-Q4_K_M-GGUF-Q4_K_M" in out
    assert "service_pin zerank-2-GGUF mradermacher/zerank-2-GGUF:Q8_0" in out
    assert "service_pins_ok" in out
    assert all(method == "GET" for method, _ in server.calls)


def test_service_pins_matches_a_bare_listing_to_its_canonical_pin(capsys: pytest.CaptureFixture[str]):
    zembed = "user.zembed-1-Q4_K_M-GGUF-Q4_K_M"
    server = _pinned_server()
    server.listed[zembed] = live.bare_model_name(zembed)

    live.run_service_pins(server, expected=PINS)

    out = capsys.readouterr().out
    assert "service_pin_alias user.zembed-1-Q4_K_M-GGUF-Q4_K_M zembed-1-Q4_K_M-GGUF-Q4_K_M" in out
    assert "service_pins_ok" in out
    assert live.bare_model_name("Qwen3.5-4B-GGUF") == "Qwen3.5-4B-GGUF"
    assert live.bare_model_name("user.") == "user."


def test_service_pins_never_match_a_listing_under_another_prefix():
    zembed = "user.zembed-1-Q4_K_M-GGUF-Q4_K_M"
    other = "extra." + live.bare_model_name(zembed)
    server = _pinned_server()
    # Another registration with the same checkpoint holds the pin under its own prefix.
    server.models[other] = {**server.models[zembed], "id": other}
    server.config["pinned_models"][server.config["pinned_models"].index(zembed)] = other
    server.loaded[other] = {**server.loaded.pop(zembed), "model_name": other}

    with pytest.raises(AssertionError, match=f"{zembed} is not pinned"):
        live.run_service_pins(server, expected=PINS)
    # A bare expected id is not widened to a prefixed listing either.
    with pytest.raises(AssertionError, match="is not pinned"):
        live.run_service_pins(server, expected=[(live.bare_model_name(zembed), "Q4_K_M")])


def test_service_pins_rejects_an_alias_that_resolves_to_another_model():
    zembed = "user.zembed-1-Q4_K_M-GGUF-Q4_K_M"
    bare = live.bare_model_name(zembed)
    server = _pinned_server()
    # A different model owns the bare name and holds the pin.
    server.models[bare] = {"id": bare, "downloaded": True, "checkpoint": "other/zembed-1-GGUF:Q4_K_M"}
    server.config["pinned_models"][server.config["pinned_models"].index(zembed)] = bare
    server.loaded[bare] = {**server.loaded.pop(zembed), "model_name": bare}

    with pytest.raises(AssertionError, match="resolve to different checkpoints"):
        live.run_service_pins(server, expected=PINS)


def test_service_pins_rejects_missing_unloaded_or_wrong_variant():
    server = _pinned_server()
    with pytest.raises(AssertionError, match="is not the Q4_K_M variant"):
        live.run_service_pins(server, expected=[("zerank-2-GGUF", "Q4_K_M")])

    server.config["pinned_models"].remove("zerank-2-GGUF")
    with pytest.raises(AssertionError, match="zerank-2-GGUF is not pinned"):
        live.run_service_pins(server, expected=PINS)

    server = _pinned_server()
    del server.loaded["zerank-2-GGUF"]
    with pytest.raises(AssertionError, match="is not loaded"):
        live.run_service_pins(server, expected=PINS)

    assert live.parse_expected_pins(["a=Q8_0"]) == [("a", "Q8_0")]
    with pytest.raises(SystemExit):
        live.parse_expected_pins(["a"])


CHAT_MODEL = "Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL"
PRESERVE_THINKING = '{"preserve_thinking":true}'


def _chat_pinned_server(*, loaded: bool = False) -> FakeLemond:
    server = FakeLemond(models=[CHAT_MODEL])
    server.config["pinned_models"].append(CHAT_MODEL)
    if loaded:
        server.loaded[CHAT_MODEL] = {"model_name": CHAT_MODEL, "pid": 300, "pinned": True, "is_busy": False}
    return server


def _qwen35moe(path: Path) -> str:
    assert path == SERVICE_GGUF
    return "qwen35moe"


def _pinned_chat(server, **kwargs):
    kwargs.setdefault("argv_of", _backend_argv())
    kwargs.setdefault("architecture_of", _qwen35moe)
    return live.run_pinned_chat(server, model=CHAT_MODEL, **kwargs)


def _gguf_string(text: str) -> bytes:
    return struct.pack("<Q", len(text.encode())) + text.encode()


def _gguf_bytes(kvs: list[tuple[str, int, bytes]]) -> bytes:
    """A GGUF v3 header with the given (key, value type, encoded value) pairs and no tensors."""
    out = b"GGUF" + struct.pack("<IQQ", 3, 0, len(kvs))
    for key, value_type, value in kvs:
        out += _gguf_string(key) + struct.pack("<I", value_type) + value
    return out


def _backend_argv(kwargs_value: str = PRESERVE_THINKING):
    return lambda pid: [
        "/opt/llama.cpp-hip-gfx1151/bin/llama-server",
        "--no-mmap",
        "--chat-template-kwargs",
        kwargs_value,
    ]


def test_pinned_chat_auto_loads_the_pinned_model_and_answers(capsys: pytest.CaptureFixture[str]):
    server = _chat_pinned_server()

    _pinned_chat(server)

    out = capsys.readouterr().out
    assert "chat_model_pinned_ok" in out
    assert "chat_completion_ok" in out
    assert "chat_template_kwargs_json_ok" in out
    assert "pinned_chat_model_loaded_ok" in out
    assert "pinned_chat_ok" in out
    # Read-only apart from the implicit load the chat request performs.
    assert [call for call in server.calls if call[0] != "GET"] == [("POST", "/chat/completions")]
    assert CHAT_MODEL in server.loaded


def test_pinned_chat_refuses_an_unpinned_or_absent_model_before_chatting():
    server = FakeLemond(models=[CHAT_MODEL])
    with pytest.raises(AssertionError, match="is not pinned"):
        _pinned_chat(server)
    assert ("POST", "/chat/completions") not in server.calls

    server = _chat_pinned_server()
    server.models[CHAT_MODEL]["downloaded"] = False
    with pytest.raises(AssertionError, match="model_not_provisioned"):
        _pinned_chat(server)
    assert ("POST", "/chat/completions") not in server.calls


def test_pinned_chat_rejects_quoted_chat_template_kwargs():
    # The 11.7.0-1 regression: the merged *_args kept the single quotes.
    server = _chat_pinned_server(loaded=True)
    with pytest.raises(AssertionError, match="chat-template-kwargs is not a JSON object"):
        _pinned_chat(server, argv_of=_backend_argv(f"'{PRESERVE_THINKING}'"))


def test_pinned_chat_fails_on_an_empty_reply_or_a_pin_load_error():
    server = _chat_pinned_server(loaded=True)
    original = server._dispatch

    def empty_reply(method, path, payload):
        if path == "/chat/completions":
            return 200, {"choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]}
        return original(method, path, payload)

    server._dispatch = empty_reply
    with pytest.raises(AssertionError, match="empty chat completion"):
        _pinned_chat(server)

    server = _chat_pinned_server(loaded=True)
    original_pins = server._dispatch

    def load_error(method, path, payload):
        status, body = original_pins(method, path, payload)
        if path == "/pins" and method == "GET":
            body["data"][0]["load_error"] = "llama-server exited with code 1"
        return status, body

    server._dispatch = load_error
    with pytest.raises(AssertionError, match="load_error"):
        _pinned_chat(server)


def _unreadable_argv(pid):
    raise AssertionError(f"backend_cmdline_unreadable: pid {pid}: Permission denied")


@pytest.mark.parametrize(
    ("argv_of", "drop_resident", "message"),
    [
        (lambda pid: ["/opt/llama.cpp-hip-gfx1151/bin/llama-server", "--no-mmap"], False, "has no --chat-template-kwargs"),
        (_unreadable_argv, False, "backend_cmdline_unreadable"),
        (_backend_argv(), True, "is not resident after the chat request"),
    ],
)
def test_pinned_chat_fails_loudly_without_backend_evidence(argv_of, drop_resident, message):
    server = _chat_pinned_server(loaded=True)
    if drop_resident:
        original = server._dispatch

        def no_residency(method, path, payload):
            status, body = original(method, path, payload)
            if path == "/health":
                body = {**body, "all_models_loaded": []}
            return status, body

        server._dispatch = no_residency
    with pytest.raises(AssertionError, match=message):
        _pinned_chat(server, argv_of=argv_of)


def test_pinned_chat_reads_the_equals_form_and_real_proc_cmdline(tmp_path: Path, capsys):
    server = _chat_pinned_server(loaded=True)
    equals_form = lambda pid: ["llama-server", f"--chat-template-kwargs={PRESERVE_THINKING}"]
    _pinned_chat(server, argv_of=equals_form)
    assert "chat_template_kwargs_json_ok" in capsys.readouterr().out

    (tmp_path / "300").mkdir()
    (tmp_path / "300" / "cmdline").write_bytes(b"llama-server\0--chat-template-kwargs\0" + PRESERVE_THINKING.encode() + b"\0")
    assert live.process_argv(300, proc_root=tmp_path) == ["llama-server", "--chat-template-kwargs", PRESERVE_THINKING]
    with pytest.raises(AssertionError, match="backend_cmdline_unreadable"):
        live.process_argv(301, proc_root=tmp_path)


def test_pinned_chat_accepts_a_reasoning_only_reply(capsys: pytest.CaptureFixture[str]):
    server = _chat_pinned_server(loaded=True)
    original = server._dispatch

    def reasoning_only(method, path, payload):
        if path == "/chat/completions":
            message = {"role": "assistant", "content": "", "reasoning_content": "Thinking."}
            return 200, {"choices": [{"message": message, "finish_reason": "stop"}]}
        return original(method, path, payload)

    server._dispatch = reasoning_only
    _pinned_chat(server)
    assert "chat_completion_ok" in capsys.readouterr().out


def test_pinned_chat_model_comes_from_the_flag_then_the_env_then_the_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv(live.PINNED_CHAT_MODEL_ENV, raising=False)
    assert live.parse_args(["pinned-chat"]).chat_model == live.DEFAULT_PINNED_CHAT_MODEL
    assert live.DEFAULT_PINNED_CHAT_MODEL == CHAT_MODEL
    monkeypatch.setenv(live.PINNED_CHAT_MODEL_ENV, "Other-Pinned-GGUF")
    assert live.parse_args(["pinned-chat"]).chat_model == "Other-Pinned-GGUF"
    assert live.parse_args(["pinned-chat", "--chat-model", "Cli-GGUF"]).chat_model == "Cli-GGUF"


def test_gguf_architecture_reads_general_architecture_past_other_keys(tmp_path: Path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(
        _gguf_bytes(
            [
                ("general.type", 8, _gguf_string("model")),
                ("general.file_type", 4, struct.pack("<I", 15)),
                ("general.tags", 9, struct.pack("<IQ", 8, 2) + _gguf_string("a") + _gguf_string("bc")),
                ("general.architecture", 8, _gguf_string("qwen35moe")),
            ]
        )
    )
    assert live.gguf_architecture(gguf) == "qwen35moe"


@pytest.mark.parametrize(
    "content",
    [b"", b"NOTGGUF-at-all", _gguf_bytes([("general.name", 8, _gguf_string("x"))])],
)
def test_gguf_architecture_fails_closed_on_unreadable_or_missing_metadata(tmp_path: Path, content: bytes):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(content)
    with pytest.raises(AssertionError, match="chat_model_architecture_unverified"):
        live.gguf_architecture(gguf)
    with pytest.raises(AssertionError, match="chat_model_architecture_unverified"):
        live.gguf_architecture(tmp_path / "absent.gguf")


def test_pinned_chat_verifies_the_qwen35_architecture_before_chatting(capsys: pytest.CaptureFixture[str]):
    server = _chat_pinned_server()
    _pinned_chat(server, architecture_of=lambda path: "qwen35")
    out = capsys.readouterr().out
    assert "chat_model_architecture qwen35" in out
    assert "chat_model_architecture_ok" in out
    assert str(SERVICE_GGUF) not in out

    server = _chat_pinned_server()
    with pytest.raises(AssertionError, match="llama is not qwen35 or qwen35moe"):
        _pinned_chat(server, architecture_of=lambda path: "llama")
    assert ("POST", "/chat/completions") not in server.calls


def test_pinned_chat_fails_closed_when_the_architecture_is_unverifiable():
    server = _chat_pinned_server()

    def unreadable(path: Path) -> str:
        raise AssertionError("chat_model_architecture_unverified: Permission denied")

    with pytest.raises(AssertionError, match="chat_model_architecture_unverified"):
        _pinned_chat(server, architecture_of=unreadable)
    assert ("POST", "/chat/completions") not in server.calls

    server = _chat_pinned_server()
    server.models[CHAT_MODEL]["recipe"] = "flm"
    with pytest.raises(AssertionError, match="not a llamacpp model"):
        _pinned_chat(server)
    assert ("POST", "/chat/completions") not in server.calls


def test_pinned_chat_requires_the_merged_preserve_thinking_default():
    # Other JSON means the qwen35/qwen35moe architecture default never merged.
    for value in ('{"enable_thinking":false}', '{"preserve_thinking":"true"}'):
        server = _chat_pinned_server(loaded=True)
        with pytest.raises(AssertionError, match="preserve_thinking"):
            _pinned_chat(server, argv_of=_backend_argv(value))


def test_pinned_chat_requires_a_stopped_reply_within_a_reasoning_safe_budget():
    with pytest.raises(ValueError, match="at least 512"):
        _pinned_chat(_chat_pinned_server(loaded=True), max_tokens=16)

    server = _chat_pinned_server(loaded=True)
    original = server._dispatch

    def truncated(method, path, payload):
        if path == "/chat/completions":
            assert payload["max_tokens"] >= 512
            message = {"role": "assistant", "content": "", "reasoning_content": "Thinking about"}
            return 200, {"choices": [{"message": message, "finish_reason": "length"}]}
        return original(method, path, payload)

    server._dispatch = truncated
    with pytest.raises(AssertionError, match="finish_reason 'length'"):
        _pinned_chat(server)


def test_nofetch_requires_journal_evidence_for_each_phase(tmp_path: Path):
    server, host = _nofetch_setup(tmp_path)
    host.journal_after = lambda cursor: ([], cursor)

    with pytest.raises(AssertionError, match="journal has no line naming"):
        live.run_nofetch(
            server,
            host=host,
            model=MODEL,
            missing_model="Tiny-Test-Model-GGUF",
            backend="rocm",
            ctx_size=4096,
            expect_checkpoint=None,
            expect_sha256=None,
            interval=0.01,
            journal_timeout=0.0,
            text=lambda client, **kwargs: None,
        )
