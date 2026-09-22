from __future__ import annotations

import argparse
import json
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
from llamacpp_server_smoke import completion_text, server_command, validate_completion


MODEL = "user.Qwen3-0.6B-Q8_0-GGUF"
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


class FakeLemond:
    """A small in-memory lemond that honors pins, busy models, one slot, and a budget."""

    def __init__(self, *, models: list[str], capacity_gb: float = 96.5) -> None:
        self.models = {name: {"id": name, "downloaded": True, "checkpoint": "Qwen/Qwen3-0.6B-GGUF:Q8_0"} for name in models}
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

    def _refuse(self, message: str) -> tuple[int, Any]:
        return 500, {"error": {"message": message}}

    def _load(self, payload: dict[str, Any]) -> tuple[int, Any]:
        name = payload["model_name"]
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
        if path == "/health":
            for name, entry in self.loaded.items():
                entry["is_busy"] = name == self.busy_model
            return 200, {"version": "11.7.0", "all_models_loaded": list(self.loaded.values())}
        if path == "/models":
            return 200, {"data": list(self.models.values())}
        if path.startswith("/models/"):
            return 200, self.models[path.removeprefix("/models/")]
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
                    {"model_name": name, "loaded": name in self.loaded, "load_error": None}
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
        expect_checkpoint="Qwen/Qwen3-0.6B-GGUF",
        owner_of=lambda path: "llama.cpp-vulkan-gfx1151",
        executable_of=lambda pid: "/opt/llama.cpp-vulkan-gfx1151/bin/llama-server",
    )

    out = capsys.readouterr().out
    for marker in ("model_provisioned_ok", "backend_selected_ok", "backend_package_ok", "completion_ok", "residency_restored"):
        assert marker in out
    assert MODEL not in server.loaded


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


def _pacman_runner(*, packagers: dict[str, str] | None = None, foreign: str = "", altered: int = 0):
    packagers = packagers or {}

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
            stdout = f"{argv[2]}: 10 total files, {altered} altered files\n"
            code = 1 if altered else 0
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


def test_provenance_rejects_mixed_foreign_altered_or_online_family():
    with pytest.raises(AssertionError, match="packager differs"):
        _run_provenance(_provenance_server(), _pacman_runner(packagers={"lemonade-app": "Other"}))
    with pytest.raises(AssertionError, match="foreign"):
        _run_provenance(_provenance_server(), _pacman_runner(foreign="lemonade-server\n"))
    with pytest.raises(AssertionError, match="altered"):
        _run_provenance(_provenance_server(), _pacman_runner(altered=1))

    online = _provenance_server()
    online.config["offline"] = False
    with pytest.raises(AssertionError, match="offline"):
        _run_provenance(online, _pacman_runner())

    bundled = _provenance_server()
    bundled.config["llamacpp"]["rocm_bin"] = "builtin"
    with pytest.raises(AssertionError, match="bundled backend"):
        _run_provenance(bundled, _pacman_runner())
