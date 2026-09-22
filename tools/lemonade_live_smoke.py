#!/usr/bin/env python3
"""Lemonade live-validation checks for the standalone Lemonade family.

Modes that target the running service (``--base-url``):

- ``text``: load a provisioned GGUF on one llama.cpp backend, complete text,
  and prove that the backend process belongs to the packaged llama.cpp.
- ``provenance``: read-only package, file-ownership, and config provenance.

Modes that start their own ``lemond`` from the packaged binary, with a
temporary cache directory, offline config, and packaged llama.cpp backends:

- ``lifecycle``: persist config, restart, and check HIP discovery.
- ``pins``: pin persistence and pinned-model startup restore.
- ``budget``: GTT-counted occupancy budget admission and refusal.
- ``displacement``: pinned and in-use models are never displaced.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Mapping
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any
from urllib import error, parse, request

from lemonade_api_auth import auth_headers, resolve_admin_api_key, resolve_api_key
from llamacpp_server_smoke import COMPLETION_PROMPT, completion_text, validate_completion


MODES = ("text", "provenance", "lifecycle", "pins", "budget", "displacement")
FAMILY_PACKAGES = (
    "lemonade",
    "lemonade-server",
    "lemonade-app",
    "llama.cpp-hip-gfx1151",
    "llama.cpp-vulkan-gfx1151",
)
BACKEND_PACKAGES = {
    "rocm": "llama.cpp-hip-gfx1151",
    "vulkan": "llama.cpp-vulkan-gfx1151",
}
DEFAULT_BACKEND_BINS = {
    "rocm": "/opt/llama.cpp-hip-gfx1151/bin",
    "vulkan": "/opt/llama.cpp-vulkan-gfx1151/bin",
}
OWNED_PATHS = {
    "/usr/bin/lemond": "lemonade-server",
    "/usr/bin/lemonade-app": "lemonade-app",
    "/usr/bin/llama-server-hip-gfx1151": "llama.cpp-hip-gfx1151",
    "/usr/bin/llama-server-vulkan-gfx1151": "llama.cpp-vulkan-gfx1151",
}
EXTRA_MODEL_STEMS = ("lemonade-live-a", "lemonade-live-b")
LIFECYCLE_SENTINEL_TIMEOUT = 777
OVERSIZED_CTX_SIZE = 4_194_304
CONFIGURED_BUDGET_GB = 0.5
BUSY_PROMPT = "Count upward from 1 to 5000, separated by commas: 1, 2, 3,"
CAPACITY_RE = re.compile(r"cannot fit within effective capacity ([0-9]+(?:\.[0-9]+)?) GB")
OWNER_RE = re.compile(r" is owned by (\S+) ")
ALTERED_RE = re.compile(r"(\d+) altered files?")


class LemonadeError(RuntimeError):
    pass


def error_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message", err))
    if err:
        return str(err)
    if payload.get("status") == "error":
        return str(payload.get("message", payload))
    return None


class LemonadeClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        admin_api_key: str | None = None,
        timeout: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.root_url = self.base_url.removesuffix("/api/v1").removesuffix("/v1")
        self.api_key = api_key
        self.admin_api_key = admin_api_key or api_key
        self.timeout = timeout

    def _request_obj(self, method: str, path: str, payload: Any) -> request.Request:
        internal = path.startswith("/internal/")
        url = (self.root_url if internal else self.base_url) + path
        headers = auth_headers(self.admin_api_key if internal else self.api_key)
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        return request.Request(url, data=data, headers=headers, method=method)

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        *,
        timeout: float | None = None,
        check: bool = True,
    ) -> tuple[int, Any]:
        req = self._request_obj(method, path, payload)
        try:
            with request.urlopen(req, timeout=timeout or self.timeout) as response:
                status = response.status
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            status = exc.code
            body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        message = error_message(parsed)
        if check and (status >= 400 or message):
            raise LemonadeError(f"{method} {path} -> {status}: {message or body[:500]}")
        return status, parsed

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)[1]

    def post(self, path: str, payload: Any, **kwargs: Any) -> Any:
        return self.request("POST", path, payload, **kwargs)[1]

    def stream_lines(self, path: str, payload: Any, *, timeout: float | None = None) -> Iterator[str]:
        req = self._request_obj("POST", path, payload)
        with request.urlopen(req, timeout=timeout or self.timeout) as response:
            for raw in response:
                yield raw.decode("utf-8", errors="replace").rstrip("\r\n")


def quote_model(model: str) -> str:
    return parse.quote(model, safe="")


def loaded_entry(health: Mapping[str, Any], model: str) -> dict[str, Any] | None:
    for item in health.get("all_models_loaded", []) or []:
        if model in {item.get("model_name"), item.get("id")}:
            return item
    return None


def model_info(client: LemonadeClient, model: str) -> dict[str, Any]:
    payload = client.get(f"/models/{quote_model(model)}")
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def load_refusal(client: LemonadeClient, model: str, **options: Any) -> str | None:
    """Try a load that should be refused; return the refusal, or None if admitted."""
    status, payload = client.request(
        "POST", "/load", {"model_name": model, **options}, check=False
    )
    message = error_message(payload)
    if status < 400 and not message:
        return None
    return message or json.dumps(payload, sort_keys=True)


def refusal_capacity_gb(message: str | None) -> float | None:
    if not message:
        return None
    match = CAPACITY_RE.search(message)
    return float(match.group(1)) if match else None


def integrated_gpu(system_info: Mapping[str, Any]) -> dict[str, Any]:
    gpus = (system_info.get("devices") or {}).get("amd_gpu") or []
    if isinstance(gpus, dict):
        gpus = [gpus]
    for gpu in gpus:
        if gpu.get("available") and (
            gpu.get("gpu_type") == "integrated" or gpu.get("integrated") is True
        ):
            return gpu
    raise AssertionError(f"no available integrated AMD GPU in system-info: {gpus!r}")


def validate_hip_discovery(system_info: Mapping[str, Any], *, expect_family: str) -> dict[str, Any]:
    gpu = integrated_gpu(system_info)
    if gpu.get("family") != expect_family:
        raise AssertionError(f"expected GPU family {expect_family}, got {gpu.get('family')!r}")
    backends = ((system_info.get("recipes") or {}).get("llamacpp") or {}).get("backends") or {}
    rocm = backends.get("rocm") or {}
    if rocm.get("state") != "installed" or "amd_gpu" not in (rocm.get("devices") or []):
        raise AssertionError(f"llamacpp rocm backend is not installed for amd_gpu: {rocm!r}")
    return gpu


def process_executable(pid: int, *, proc_root: Path = Path("/proc")) -> str:
    raw = (proc_root / str(pid) / "cmdline").read_bytes()
    argv0 = raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")
    if not argv0:
        raise AssertionError(f"process {pid} has no readable argv[0]")
    if not argv0.startswith("/"):
        resolved = shutil.which(argv0)
        if resolved is None:
            raise AssertionError(f"process {pid} argv[0] {argv0!r} is not an absolute path")
        argv0 = resolved
    return argv0


Runner = Callable[..., subprocess.CompletedProcess]


def run_command(
    argv: list[str],
    *,
    runner: Runner = subprocess.run,
    ok_codes: frozenset[int] = frozenset({0}),
) -> str:
    completed = runner(argv, capture_output=True, text=True)
    if completed.returncode not in ok_codes:
        raise AssertionError(
            f"{' '.join(argv)} exited {completed.returncode}: {completed.stderr.strip()}"
        )
    return completed.stdout


def package_owner(path: str | Path, *, runner: Runner = subprocess.run) -> str:
    output = run_command(["pacman", "-Qo", str(path)], runner=runner)
    match = OWNER_RE.search(output)
    if match is None:
        raise AssertionError(f"could not parse pacman -Qo output: {output!r}")
    return match.group(1)


def parse_pacman_info(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[:1].isspace() and key is not None:
            fields[key] += " " + line.strip()
            continue
        name, sep, value = line.partition(":")
        if not sep:
            continue
        key = name.strip()
        fields[key] = value.strip()
    return fields


def run_text(
    client: LemonadeClient,
    *,
    model: str,
    backend: str,
    ctx_size: int,
    expect_checkpoint: str | None,
    owner_of: Callable[[str], str] = package_owner,
    executable_of: Callable[[int], str] = process_executable,
) -> None:
    info = model_info(client, model)
    if not info.get("downloaded"):
        raise AssertionError(
            f"model_not_provisioned: {model}; provision it explicitly before the "
            "validation window instead of letting a load download it"
        )
    if expect_checkpoint and expect_checkpoint not in json.dumps(
        info.get("checkpoints") or info.get("checkpoint")
    ):
        raise AssertionError(f"{model} checkpoint does not come from {expect_checkpoint}: {info!r}")
    print("model_provisioned_ok")

    was_loaded = loaded_entry(client.get("/health"), model) is not None
    try:
        client.post("/load", {"model_name": model, "llamacpp_backend": backend, "ctx_size": ctx_size})
        entry = loaded_entry(client.get("/health"), model)
        if entry is None:
            raise AssertionError(f"{model} is not resident after load")
        selected = (entry.get("recipe_options") or {}).get("llamacpp_backend")
        if selected != backend:
            raise AssertionError(f"expected llamacpp_backend {backend}, got {selected!r}")
        print("backend_selected", backend)
        print("backend_selected_ok")

        executable = executable_of(int(entry["pid"]))
        owner = owner_of(executable)
        print("backend_executable", executable)
        print("backend_package", owner)
        if owner != BACKEND_PACKAGES[backend]:
            raise AssertionError(f"backend process is owned by {owner}, not {BACKEND_PACKAGES[backend]}")
        print("backend_package_ok")

        payload = client.post(
            "/completions",
            {"model": model, "prompt": COMPLETION_PROMPT, "max_tokens": 8, "temperature": 0},
        )
        text = completion_text(payload)
        print("completion_text", json.dumps(text))
        validate_completion(text)
        print("completion_ok")
    finally:
        if not was_loaded:
            client.request("POST", "/unload", {"model_name": model}, check=False)
            print("residency_restored")


def run_provenance(
    client: LemonadeClient,
    *,
    repo: str,
    service: str,
    runner: Runner = subprocess.run,
    executable_of: Callable[[int], str] = process_executable,
    path_is_dir: Callable[[Path], bool] = Path.is_dir,
) -> None:
    packagers: set[str] = set()
    for package in FAMILY_PACKAGES:
        local = parse_pacman_info(run_command(["pacman", "-Qi", package], runner=runner))
        synced = parse_pacman_info(run_command(["pacman", "-Si", f"{repo}/{package}"], runner=runner))
        if local.get("Version") != synced.get("Version"):
            raise AssertionError(
                f"{package} installed {local.get('Version')} differs from {repo} {synced.get('Version')}"
            )
        if local.get("Packager") != synced.get("Packager"):
            raise AssertionError(f"{package} installed packager differs from the {repo} build")
        packagers.add(local.get("Packager", ""))
        print("package_from_repo", package, local.get("Version"))
    if len(packagers) != 1:
        raise AssertionError(f"mixed packagers across the Lemonade family: {len(packagers)} identities")
    print("family_packager_uniform_ok")

    foreign = set(run_command(["pacman", "-Qmq"], runner=runner, ok_codes=frozenset({0, 1})).split())
    if foreign & set(FAMILY_PACKAGES):
        raise AssertionError(f"foreign Lemonade family packages: {sorted(foreign & set(FAMILY_PACKAGES))}")
    print("no_foreign_package_ok")

    for path, expected in OWNED_PATHS.items():
        owner = package_owner(path, runner=runner)
        if owner != expected:
            raise AssertionError(f"{path} is owned by {owner}, not {expected}")
        print("owned", path, owner)
    main_pid = int(
        run_command(["systemctl", "show", "-p", "MainPID", "--value", service], runner=runner).strip() or 0
    )
    if main_pid <= 0:
        raise AssertionError(f"{service} has no running main process")
    service_executable = executable_of(main_pid)
    service_owner = package_owner(service_executable, runner=runner)
    if service_owner != "lemonade-server":
        raise AssertionError(f"{service} runs {service_executable} owned by {service_owner}")
    print("service_executable", service_executable)
    print("service_executable_owned_ok")

    for package in FAMILY_PACKAGES:
        output = run_command(["pacman", "-Qkk", package], runner=runner, ok_codes=frozenset({0, 1}))
        match = ALTERED_RE.search(output)
        if match is None or int(match.group(1)) != 0:
            raise AssertionError(f"pacman -Qkk {package} reported altered files: {output.strip()}")
    print("package_files_unaltered_ok")

    config = client.get("/internal/config")
    for key in ("offline", "no_fetch_executables"):
        if config.get(key) is not True:
            raise AssertionError(f"service config {key} is {config.get(key)!r}, expected true")
    print("offline_config_ok")
    llamacpp = config.get("llamacpp") or {}
    for backend, expected in BACKEND_PACKAGES.items():
        value = str(llamacpp.get(f"{backend}_bin", ""))
        if not value.startswith("/"):
            raise AssertionError(
                f"llamacpp.{backend}_bin={value!r} is not a packaged path; Lemonade could fetch a bundled backend"
            )
        target = Path(value)
        if path_is_dir(target):
            target = target / "llama-server"
        owner = package_owner(target, runner=runner)
        if owner != expected:
            raise AssertionError(f"llamacpp.{backend}_bin resolves to {owner}, not {expected}")
    print("no_bundled_backend_ok")
    print("provenance_ok")


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def isolated_config(
    *,
    host: str,
    port: int,
    models_dir: Path,
    extra_models_dir: Path,
    backend_bins: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "host": host,
        "port": port,
        "log_level": "debug",
        "broadcast": False,
        "inhibit_suspend": False,
        "offline": True,
        "no_fetch_executables": True,
        "auto_check_model_updates": False,
        "max_loaded_models": 1,
        "max_gpu_memory_occupancy_gb": -1.0,
        "pinned_models": [],
        "models_dir": str(models_dir),
        "extra_models_dir": str(extra_models_dir),
        "llamacpp": {
            "backend": "rocm",
            "prefer_system": True,
            "rocm_bin": backend_bins["rocm"],
            "vulkan_bin": backend_bins["vulkan"],
        },
    }


class IsolatedLemond:
    """A private lemond with its own cache dir; nothing outlives the context."""

    def __init__(self, args: argparse.Namespace, *, gguf: Path | None = None) -> None:
        self.args = args
        self.gguf = gguf
        self.proc: subprocess.Popen | None = None
        self.root: Path | None = None
        self.log_handle: Any = None
        self.client = LemonadeClient("http://unused", timeout=args.request_timeout)

    @property
    def cache_dir(self) -> Path:
        assert self.root is not None
        return self.root / "cache"

    def __enter__(self) -> "IsolatedLemond":
        self.root = Path(tempfile.mkdtemp(prefix="lemonade-live-"))
        extra_dir = self.root / "extra-models"
        extra_dir.mkdir()
        (self.root / "models").mkdir()
        self.cache_dir.mkdir()
        if self.gguf is not None:
            for stem in EXTRA_MODEL_STEMS:
                (extra_dir / f"{stem}.gguf").symlink_to(self.gguf.resolve())
        port = self.args.port or _free_port(self.args.host)
        config = isolated_config(
            host=self.args.host,
            port=port,
            models_dir=self.root / "models",
            extra_models_dir=extra_dir,
            backend_bins={"rocm": self.args.rocm_bin, "vulkan": self.args.vulkan_bin},
        )
        (self.cache_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
        self.client = LemonadeClient(
            f"http://{self.args.host}:{port}/api/v1", timeout=self.args.request_timeout
        )
        if self.args.server_log is not None:
            self.args.server_log.parent.mkdir(parents=True, exist_ok=True)
            self.log_handle = self.args.server_log.open("a", encoding="utf-8")
        self.port = port
        try:
            self.start()
        except BaseException:
            # `with` skips __exit__ when __enter__ raises; never orphan lemond.
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc_info: Any) -> None:
        try:
            self.stop()
        finally:
            if self.log_handle is not None:
                self.log_handle.close()
            if self.root is not None:
                shutil.rmtree(self.root, ignore_errors=True)

    def config_file(self) -> dict[str, Any]:
        return json.loads((self.cache_dir / "config.json").read_text(encoding="utf-8"))

    def start(self) -> None:
        env = {key: value for key, value in os.environ.items() if not key.startswith("LEMONADE_")}
        self.proc = subprocess.Popen(
            [
                self.args.lemond,
                str(self.cache_dir),
                "--host",
                self.args.host,
                "--port",
                str(self.port),
            ],
            stdout=self.log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        deadline = time.monotonic() + self.args.startup_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"isolated lemond exited during startup with {self.proc.returncode}")
            try:
                self.client.get("/health", timeout=5.0)
                return
            except (LemonadeError, error.URLError, OSError) as exc:
                last_error = exc
                time.sleep(0.5)
        raise TimeoutError(f"isolated lemond did not become healthy: {last_error}")

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            self.client.request("POST", "/internal/shutdown", {}, timeout=10.0, check=False)
        except (error.URLError, OSError):
            pass
        for action in (None, self.proc.terminate, self.proc.kill):
            if action is not None:
                action()
            try:
                self.proc.wait(timeout=15.0)
                return
            except subprocess.TimeoutExpired:
                continue

    def restart(self) -> None:
        self.stop()
        self.start()

    def extra_model(self, stem: str) -> str:
        payload = self.client.get("/models")
        ids = [str(item.get("id")) for item in payload.get("data", [])]
        for candidate in (f"extra.{stem}", f"extra.{stem}.gguf"):
            if candidate in ids:
                return candidate
        raise AssertionError(f"extra model {stem} not discovered; extra models: {[i for i in ids if i.startswith('extra.')]}")


def _require_resident(client: LemonadeClient, model: str, *, pid: Any = None) -> dict[str, Any]:
    entry = loaded_entry(client.get("/health"), model)
    if entry is None:
        raise AssertionError(f"{model} was displaced")
    if pid is not None and entry.get("pid") != pid:
        raise AssertionError(f"{model} backend was replaced: pid {pid} -> {entry.get('pid')}")
    return entry


def _require_not_resident(client: LemonadeClient, model: str) -> None:
    if loaded_entry(client.get("/health"), model) is not None:
        raise AssertionError(f"{model} became resident after a refused load")


def run_lifecycle(inst: IsolatedLemond, *, expect_family: str) -> None:
    health = inst.client.get("/health")
    print("lemond_version", health.get("version"))
    print("isolated_server_started")
    gpu = validate_hip_discovery(inst.client.get("/system-info"), expect_family=expect_family)
    print("hip_device", json.dumps(gpu.get("name")), gpu.get("family"))
    print("hip_discovery_ok")

    inst.client.post("/internal/set", {"global_timeout": LIFECYCLE_SENTINEL_TIMEOUT})
    if inst.config_file().get("global_timeout") != LIFECYCLE_SENTINEL_TIMEOUT:
        raise AssertionError("config change was not persisted to config.json")
    print("config_persisted_ok")
    before = inst.client.get("/internal/config")
    inst.restart()
    print("isolated_server_restarted")
    after = inst.client.get("/internal/config")
    changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    if changed or after.get("global_timeout") != LIFECYCLE_SENTINEL_TIMEOUT:
        raise AssertionError(f"config changed across restart: {changed}")
    print("config_preserved_ok")


def _wait_for_pin_restore(client: LemonadeClient, model: str, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for pin in client.get("/pins").get("data", []):
            if pin.get("model_name") != model:
                continue
            if pin.get("load_error"):
                raise AssertionError(f"pinned model failed to restore: {pin['load_error']}")
            if pin.get("loaded"):
                return
        time.sleep(1.0)
    raise AssertionError(f"pinned model {model} was not restored within {timeout:.0f}s")


def run_pins(inst: IsolatedLemond, *, ctx_size: int, timeout: float) -> None:
    model = inst.extra_model(EXTRA_MODEL_STEMS[0])
    inst.client.post("/load", {"model_name": model, "ctx_size": ctx_size})
    inst.client.post("/pins", {"model_name": model})
    if model not in inst.config_file().get("pinned_models", []):
        raise AssertionError("pin was not persisted to config.json pinned_models")
    print("pin_persisted_ok")

    inst.restart()
    print("isolated_server_restarted")
    _wait_for_pin_restore(inst.client, model, timeout=timeout)
    print("pin_restored_ok")
    if not _require_resident(inst.client, model).get("pinned"):
        raise AssertionError("restored model is resident but not pinned")
    print("pin_restored_pinned_ok")

    inst.client.request("DELETE", f"/pins/{quote_model(model)}")
    if model in inst.config_file().get("pinned_models", []):
        raise AssertionError("unpin did not remove the persisted pin")
    print("pin_removed_ok")


def run_budget(inst: IsolatedLemond, *, ctx_size: int) -> None:
    gpu = integrated_gpu(inst.client.get("/system-info"))
    vram_gb = float(gpu.get("vram_gb", 0.0))
    gtt_gb = float(gpu.get("virtual_mem_gb", 0.0))
    print("apu_memory_pools", f"vram_gb={vram_gb:.2f}", f"gtt_gb={gtt_gb:.2f}")
    if gtt_gb <= 0:
        raise AssertionError("integrated GPU reports no GTT pool (virtual_mem_gb)")
    print("apu_gtt_reported_ok")

    model = inst.extra_model(EXTRA_MODEL_STEMS[0])
    refusal = load_refusal(inst.client, model, ctx_size=OVERSIZED_CTX_SIZE)
    capacity_gb = refusal_capacity_gb(refusal)
    print("budget_refusal", json.dumps(refusal))
    if capacity_gb is None:
        raise AssertionError("oversized load was not refused by the occupancy budget")
    _require_not_resident(inst.client, model)
    print("budget_refuse_ok")
    print("effective_capacity_gb", f"{capacity_gb:.2f}")
    if capacity_gb <= vram_gb:
        raise AssertionError(
            f"effective capacity {capacity_gb} GB does not exceed dedicated VRAM {vram_gb} GB"
        )
    print("gtt_counted_ok")

    inst.client.post("/load", {"model_name": model, "ctx_size": ctx_size})
    _require_resident(inst.client, model)
    print("budget_admit_ok")

    inst.client.post("/unload", {"model_name": model})
    inst.client.post("/internal/set", {"max_gpu_memory_occupancy_gb": CONFIGURED_BUDGET_GB})
    refusal = load_refusal(inst.client, model, ctx_size=ctx_size)
    print("configured_budget_refusal", json.dumps(refusal))
    if refusal_capacity_gb(refusal) != CONFIGURED_BUDGET_GB:
        raise AssertionError("configured occupancy budget did not bound admission")
    _require_not_resident(inst.client, model)
    print("configured_budget_refuse_ok")


class BusyStream:
    """Keep one model in use with a streaming completion on a worker thread."""

    def __init__(self, client: LemonadeClient, model: str, *, max_tokens: int) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.started = threading.Event()
        self.chunks = 0
        self.finished = False
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        payload = {
            "model": self.model,
            "prompt": BUSY_PROMPT,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "stream": True,
        }
        try:
            for line in self.client.stream_lines("/completions", payload):
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    self.finished = True
                    break
                self.chunks += 1
                self.started.set()
        except BaseException as exc:  # noqa: BLE001 - surfaced by the caller.
            self.error = exc
        finally:
            self.started.set()

    def __enter__(self) -> "BusyStream":
        self.thread.start()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.thread.join(timeout=self.client.timeout)

    def wait_started(self, timeout: float) -> None:
        if not self.started.wait(timeout) or self.chunks == 0:
            raise AssertionError(f"busy stream did not start: {self.error!r}")


def run_displacement(inst: IsolatedLemond, *, ctx_size: int, stream_tokens: int) -> None:
    client = inst.client
    first, second = (inst.extra_model(stem) for stem in EXTRA_MODEL_STEMS)

    client.post("/load", {"model_name": first, "ctx_size": ctx_size})
    client.post("/pins", {"model_name": first})
    pid = _require_resident(client, first)["pid"]
    refusal = load_refusal(client, second, ctx_size=ctx_size)
    print("pinned_refusal", json.dumps(refusal))
    if refusal is None:
        raise AssertionError("loading a second model displaced the pinned model")
    _require_resident(client, first, pid=pid)
    _require_not_resident(client, second)
    print("pinned_not_displaced_ok")

    client.request("DELETE", f"/pins/{quote_model(first)}")
    with BusyStream(client, first, max_tokens=stream_tokens) as stream:
        stream.wait_started(timeout=client.timeout)
        if not _require_resident(client, first, pid=pid).get("is_busy"):
            raise AssertionError("busy_window_missed: the stream ended before the displacement attempt")
        print("busy_window_ok")
        refusal = load_refusal(client, second, ctx_size=ctx_size)
        print("in_use_refusal", json.dumps(refusal))
        if refusal is None:
            raise AssertionError("loading a second model displaced the in-use model")
        _require_resident(client, first, pid=pid)
        print("in_use_not_displaced_ok")
    if stream.error is not None or not stream.finished:
        raise AssertionError(f"in-use request did not complete cleanly: {stream.error!r}")
    print("busy_request_completed_ok")

    client.post("/load", {"model_name": second, "ctx_size": ctx_size})
    _require_resident(client, second)
    if loaded_entry(client.get("/health"), first) is not None:
        raise AssertionError("idle unpinned model was not displaced; refusals are not attributable")
    print("idle_displacement_control_ok")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Lemonade live-validation check.")
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--base-url", default="http://127.0.0.1:13305/api/v1")
    parser.add_argument("--model", help="Lemonade model id for text mode")
    parser.add_argument("--expect-checkpoint", help="checkpoint source the text model must use")
    parser.add_argument("--backend", choices=sorted(BACKEND_PACKAGES), default="rocm")
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--gguf", type=Path, help="local GGUF file for isolated modes")
    parser.add_argument("--lemond", default="/usr/bin/lemond")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--rocm-bin", default=DEFAULT_BACKEND_BINS["rocm"])
    parser.add_argument("--vulkan-bin", default=DEFAULT_BACKEND_BINS["vulkan"])
    parser.add_argument("--expect-gpu-family", default="gfx1151")
    parser.add_argument("--repo", default="strix-halo-gfx1151")
    parser.add_argument("--service", default="lemond.service")
    parser.add_argument("--server-log", type=Path)
    parser.add_argument("--stream-tokens", type=int, default=2048)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--request-timeout", type=float, default=600.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    print("mode", args.mode)
    if args.mode in {"text", "provenance"}:
        client = LemonadeClient(
            args.base_url,
            api_key=resolve_api_key(),
            admin_api_key=resolve_admin_api_key(),
            timeout=args.request_timeout,
        )
        if args.mode == "text":
            if not args.model:
                raise SystemExit("text mode requires --model")
            run_text(
                client,
                model=args.model,
                backend=args.backend,
                ctx_size=args.ctx_size,
                expect_checkpoint=args.expect_checkpoint,
            )
        else:
            run_provenance(client, repo=args.repo, service=args.service)
        return

    needs_gguf = args.mode != "lifecycle"
    if needs_gguf and (args.gguf is None or not args.gguf.is_file()):
        raise SystemExit(f"{args.mode} mode requires --gguf pointing at a local GGUF file")
    with IsolatedLemond(args, gguf=args.gguf if needs_gguf else None) as inst:
        if args.mode == "lifecycle":
            run_lifecycle(inst, expect_family=args.expect_gpu_family)
        elif args.mode == "pins":
            run_pins(inst, ctx_size=args.ctx_size, timeout=args.startup_timeout)
        elif args.mode == "budget":
            run_budget(inst, ctx_size=args.ctx_size)
        else:
            run_displacement(inst, ctx_size=args.ctx_size, stream_tokens=args.stream_tokens)


if __name__ == "__main__":
    main()
