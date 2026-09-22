#!/usr/bin/env python3
"""Lemonade live-validation checks for the standalone Lemonade family.

Modes that target the running service (``--base-url``):

- ``text``: load a provisioned GGUF on one llama.cpp backend, complete text,
  and prove that the backend process and every ROCm/HIP/ggml/llama shared
  object it maps belong to repo packages, none from lemond's cache.
- ``provenance``: read-only package, file-ownership, and config provenance.
- ``nofetch``: load a pre-placed model and request an absent one while
  watching the service journal, the model and backend caches, and lemond's
  sockets. The pre-placed load may log no download; the absent model must fail
  loudly with unchanged caches and no non-loopback connection, and a logged,
  blackholed download attempt is recorded rather than failed.
- ``service-pins``: read-only check that consumer models are pinned and loaded.

Modes that start their own ``lemond`` from the packaged binary, with a
temporary cache directory, offline config, and packaged llama.cpp backends:

- ``lifecycle``: persist config, restart, and check HIP discovery.
- ``pins``: pin persistence and pinned-model startup restore.
- ``budget``: GTT-counted occupancy budget admission and refusal.
- ``displacement``: pinned and in-use models are never displaced.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Iterator, Mapping
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any
from urllib import error, parse, request

from lemonade_api_auth import auth_headers, resolve_admin_api_key, resolve_api_key
from llamacpp_server_smoke import (
    COMPLETION_PROMPT,
    completion_text,
    file_sha256,
    validate_completion,
    verify_sha256,
)


SERVICE_MODES = ("text", "provenance", "nofetch", "service-pins")
MODES = (*SERVICE_MODES, "lifecycle", "pins", "budget", "displacement")
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
# Shared objects whose provenance the text scenarios prove: llama.cpp's own
# libraries and the ROCm/HIP runtime stack a backend can pull in.
BACKEND_LIB_RE = re.compile(
    r"^lib(?:ggml|llama|mtmd|amdhip|hip|hsa|roc|amd_comgr|rccl|miopen)[^/]*\.so(?:\.[0-9.]+)?$",
    re.IGNORECASE,
)
LLAMACPP_LIB_RE = re.compile(r"^lib(?:ggml|llama|mtmd)", re.IGNORECASE)
HIP_RUNTIME_LIB_RE = re.compile(r"^libamdhip64\.so")
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


def main_checkpoint(info: Mapping[str, Any]) -> str | None:
    checkpoints = info.get("checkpoints")
    if isinstance(checkpoints, dict) and checkpoints.get("main"):
        return str(checkpoints["main"])
    checkpoint = info.get("checkpoint")
    return str(checkpoint) if checkpoint else None


def main_model_file(client: LemonadeClient, model: str) -> Path:
    """Resolve the service's local main model file; the path is never printed."""
    payload = client.get(f"/models/{quote_model(model)}/files?include_paths=true")
    for item in payload.get("files", []):
        if item.get("role") == "main" and item.get("exists") and item.get("path"):
            return Path(str(item["path"]))
    raise AssertionError(f"{model} has no resolved main model file")


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


def repo_package_names(repo: str, *, runner: Runner = subprocess.run) -> set[str]:
    return set(run_command(["pacman", "-Slq", repo], runner=runner).split())


def mapped_libraries(pid: int, *, proc_root: Path = Path("/proc")) -> set[str]:
    """Paths of the ROCm/HIP/ggml/llama shared objects mapped into `pid`."""
    try:
        text = (proc_root / str(pid) / "maps").read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise AssertionError(
            f"backend_maps_unreadable: {exc.strerror}; run with privileges that can "
            "read the backend process's memory map"
        ) from None
    paths: set[str] = set()
    for line in text.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6:
            continue
        path = fields[5].strip().removesuffix(" (deleted)")
        if path.startswith("/") and BACKEND_LIB_RE.match(Path(path).name):
            paths.add(path)
    return paths


def _under(path: str, roots: Iterable[Path]) -> bool:
    candidate = Path(path)
    for root in roots:
        for base in {root, Path(os.path.realpath(root))}:
            if candidate.is_relative_to(base):
                return True
    return False


def verify_backend_libraries(
    paths: set[str],
    *,
    backend: str,
    repo: str,
    repo_packages: set[str],
    cache_bins: Iterable[Path],
    owner_of: Callable[[str], str],
) -> None:
    """Every mapped ROCm/HIP/ggml/llama object must come from a repo package.

    With backend=rocm, lemond prepends cached TheRock lib dirs to the backend's
    LD_LIBRARY_PATH, so a cached runtime can shadow the packaged one even when
    the executable is packaged. Output carries counts and package names only.
    """
    names = [Path(path).name for path in paths]
    print("backend_libraries", len(paths))
    if not any(LLAMACPP_LIB_RE.match(name) for name in names):
        raise AssertionError("backend_libraries_missing: no ggml or llama shared object is mapped")
    if backend == "rocm" and not any(HIP_RUNTIME_LIB_RE.match(name) for name in names):
        raise AssertionError("backend_libraries_missing: the rocm backend has no HIP runtime mapped")
    cached = [path for path in paths if _under(path, cache_bins)]
    print("backend_libraries_from_cache", len(cached))
    if cached:
        raise AssertionError(f"{len(cached)} backend libraries load from lemond's cache bin directory")
    owners: dict[str, int] = {}
    unowned = 0
    llamacpp_owners: set[str] = set()
    for path in sorted(paths):
        try:
            owner = owner_of(path)
        except AssertionError:
            unowned += 1
            continue
        owners[owner] = owners.get(owner, 0) + 1
        if LLAMACPP_LIB_RE.match(Path(path).name):
            llamacpp_owners.add(owner)
    print("backend_libraries_unowned", unowned)
    if unowned:
        raise AssertionError(f"{unowned} backend libraries are not owned by any package")
    for owner, count in sorted(owners.items()):
        print("backend_library_package", owner, count)
    outside = sorted(set(owners) - repo_packages)
    if outside:
        raise AssertionError(f"backend libraries owned by packages outside {repo}: {outside}")
    if llamacpp_owners != {BACKEND_PACKAGES[backend]}:
        raise AssertionError(
            f"ggml/llama libraries are owned by {sorted(llamacpp_owners)}, not {BACKEND_PACKAGES[backend]}"
        )
    print("backend_libraries_repo_owned_ok")


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
    expect_sha256: str | None = None,
    repo: str = "strix-halo-gfx1151",
    cache_bins: Iterable[Path] = (),
    owner_of: Callable[[str], str] = package_owner,
    executable_of: Callable[[int], str] = process_executable,
    digest_of: Callable[[Path], str] = file_sha256,
    libraries_of: Callable[[int], set[str]] = mapped_libraries,
    repo_packages_of: Callable[[str], set[str]] = repo_package_names,
) -> None:
    info = model_info(client, model)
    if not info.get("downloaded"):
        raise AssertionError(
            f"model_not_provisioned: {model}; provision it explicitly before the "
            "validation window instead of letting a load download it"
        )
    checkpoint = main_checkpoint(info)
    if expect_checkpoint and checkpoint != expect_checkpoint:
        raise AssertionError(f"{model} checkpoint is {checkpoint!r}, not {expect_checkpoint!r}")
    if expect_sha256:
        path = main_model_file(client, model)
        actual = digest_of(path)
        if actual != expect_sha256.lower():
            raise AssertionError(
                f"model_sha256 mismatch for {model}: expected {expect_sha256}, got {actual}"
            )
        print("model_sha256_ok")
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

        # After a completion, so lazily loaded backend libraries are mapped too.
        verify_backend_libraries(
            libraries_of(int(entry["pid"])),
            backend=backend,
            repo=repo,
            repo_packages=repo_packages_of(repo),
            cache_bins=cache_bins,
            owner_of=owner_of,
        )
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


# --- No-fetch evidence (service) --------------------------------------------

BLACKHOLE_ENV_KEYS = ("HF_ENDPOINT", "MODELSCOPE_ENDPOINT")
# Log lines that the candidate emits only while downloading or installing a
# model or backend. "downloaded=" and "already downloaded" do not match.
FETCH_LOG_RE = re.compile(
    r"(?i)(?:\bdownloading\b|download complete|\bdownloaded(?::| archive| tarball)"
    r"|all files downloaded|not cached, downloading|fetching repository"
    r"|\binstalling\b|installation complete|\bupgrading\b|\breinstalling\b)"
)
SS_USERS_RE = re.compile(r"pid=(\d+)")


def _peer_host_port(address: str) -> tuple[str, str]:
    host, _, port = address.rpartition(":")
    host = host.strip("[]").split("%", 1)[0]
    return host, port


def is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def blackhole_ports(env: Mapping[str, str]) -> set[str]:
    """Require every download endpoint to point at loopback; return its ports."""
    ports: set[str] = set()
    for key in BLACKHOLE_ENV_KEYS:
        value = env.get(key, "")
        parsed = parse.urlsplit(value)
        if not parsed.hostname or not is_loopback_host(parsed.hostname):
            raise AssertionError(
                f"endpoint_blackhole_missing: the service's {key} must name a loopback "
                "endpoint so a download attempt cannot leave the host"
            )
        ports.add(str(parsed.port or (443 if parsed.scheme == "https" else 80)))
    return ports


def parse_ss(text: str) -> list[dict[str, Any]]:
    """Parse `ss -tanpH` rows into state, local port, peer, and owning pids."""
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        local_port = _peer_host_port(fields[3])[1]
        host, port = _peer_host_port(fields[4])
        pids = {int(pid) for pid in SS_USERS_RE.findall(" ".join(fields[5:]))}
        rows.append(
            {"state": fields[0], "local_port": local_port, "peer_host": host, "peer_port": port, "pids": pids}
        )
    return rows


def snapshot_tree(root: Path) -> dict[str, tuple[Any, ...]]:
    """List a cache tree by relative path, type, size, and mtime; hashing is too slow."""
    if not root.exists():
        return {}
    entries: dict[str, tuple[Any, ...]] = {}

    def fail(exc: OSError) -> None:
        raise AssertionError(f"cache_unreadable: {exc.strerror}; run with read access to the service caches")

    for dirpath, dirnames, filenames in os.walk(root, onerror=fail):
        base = Path(dirpath)
        for name in [*dirnames, *filenames]:
            path = base / name
            rel = str(path.relative_to(root))
            st = path.lstat()
            if path.is_symlink():
                entries[rel] = ("link", os.readlink(path))
            elif path.is_dir():
                entries[rel] = ("dir",)
            else:
                entries[rel] = ("file", st.st_size, st.st_mtime_ns)
    return entries


def tree_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


class ServiceHost:
    """Read-only views of the systemd service: pids, env, journal, sockets, caches."""

    def __init__(self, service: str, *, runner: Runner = subprocess.run, proc_root: Path = Path("/proc")) -> None:
        self.service = service
        self.runner = runner
        self.proc_root = proc_root

    def show(self, prop: str) -> str:
        return run_command(
            ["systemctl", "show", "-p", prop, "--value", self.service], runner=self.runner
        ).strip()

    def main_pid(self) -> int:
        pid = int(self.show("MainPID") or 0)
        if pid <= 0:
            raise AssertionError(f"{self.service} has no running main process")
        return pid

    def process_tree(self, pid: int) -> set[int]:
        pids, pending = set(), [pid]
        while pending:
            current = pending.pop()
            pids.add(current)
            for children in (self.proc_root / str(current) / "task").glob("*/children"):
                try:
                    pending += [int(child) for child in children.read_text().split()]
                except OSError:
                    continue
        return pids

    def service_env(self, keys: tuple[str, ...]) -> dict[str, str]:
        """Read only `keys`: unit Environment= first, then /proc environ if readable."""
        env: dict[str, str] = {}
        for item in shlex.split(self.show("Environment")):
            key, sep, value = item.partition("=")
            if sep and key in keys:
                env[key] = value
        if all(key in env for key in keys):
            return env
        try:
            raw = (self.proc_root / str(self.main_pid()) / "environ").read_bytes()
        except OSError:
            return env
        for item in raw.split(b"\0"):
            key, sep, value = item.decode("utf-8", errors="replace").partition("=")
            if sep and key in keys:
                env.setdefault(key, value)
        return env

    def endpoint_env(self) -> dict[str, str]:
        return self.service_env(BLACKHOLE_ENV_KEYS)

    def cache_dir(self) -> Path:
        """The service's cache dir: lemond's positional argv, LEMONADE_CACHE_DIR, then ~user."""
        argv = (self.proc_root / str(self.main_pid()) / "cmdline").read_bytes().split(b"\0")
        if len(argv) > 1 and argv[1] and not argv[1].startswith(b"-"):
            return Path(argv[1].decode())
        env_dir = self.service_env(("LEMONADE_CACHE_DIR",)).get("LEMONADE_CACHE_DIR")
        if env_dir:
            return Path(env_dir)
        return Path(pwd.getpwnam(self.show("User") or "root").pw_dir) / ".cache" / "lemonade"

    def sockets(self) -> list[dict[str, Any]]:
        return parse_ss(run_command(["ss", "-tanpH"], runner=self.runner))

    def journal_since(self, since: float) -> list[str]:
        output = run_command(
            ["journalctl", "-u", self.service, "--since", f"@{int(since)}", "--no-pager", "-q", "-o", "short-unix"],
            runner=self.runner,
        )
        lines = []
        for line in output.splitlines():
            stamp, _, rest = line.partition(" ")
            try:
                if float(stamp) < since:
                    continue
            except ValueError:
                pass
            lines.append(rest)
        return lines


class FetchWatch:
    """Observe one phase: cache trees, service journal, and lemond-tree sockets."""

    def __init__(
        self,
        host: ServiceHost,
        *,
        caches: Mapping[str, Path],
        blackhole: set[str],
        expect_log: str,
        interval: float = 0.2,
        journal_timeout: float = 10.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.host = host
        self.expect_log = expect_log
        self.journal_timeout = journal_timeout
        self.caches = caches
        self.blackhole = blackhole
        self.interval = interval
        self.clock = clock
        self.remote: set[tuple[str, str]] = set()
        self.blackhole_hits = 0
        self.samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.error: BaseException | None = None

    def sample(self) -> None:
        tree = self.host.process_tree(self.host.main_pid())
        rows = self.host.sockets()
        # Clients may reach the service over the LAN; accepted connections are not fetches.
        listen_ports = {r["local_port"] for r in rows if r["state"] == "LISTEN" and r["pids"] & tree}
        for row in rows:
            if row["state"] == "LISTEN" or not row["pids"] & tree or row["local_port"] in listen_ports:
                continue
            if not is_loopback_host(row["peer_host"]):
                self.remote.add((row["peer_host"], row["peer_port"]))
            elif row["peer_port"] in self.blackhole:
                self.blackhole_hits += 1
        self.samples += 1

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.sample()
            except BaseException as exc:  # noqa: BLE001 - surfaced by verify().
                self.error = exc
                return
            self._stop.wait(self.interval)

    def __enter__(self) -> "FetchWatch":
        self.before = {name: snapshot_tree(path) for name, path in self.caches.items()}
        self.since = self.clock()
        self._thread.start()
        return self

    def _collect(self) -> None:
        self._stop.set()
        self._thread.join(timeout=30.0)
        self.sample()
        self.after = {name: snapshot_tree(path) for name, path in self.caches.items()}
        # journald can trail the HTTP response; wait until the phase's own line lands.
        deadline = time.monotonic() + self.journal_timeout
        while True:
            self.journal = self.host.journal_since(self.since)
            if any(self.expect_log in line for line in self.journal) or time.monotonic() >= deadline:
                return
            time.sleep(0.5)

    def __exit__(self, exc_type: Any, *exc_info: Any) -> None:
        try:
            self._collect()
        except BaseException:
            if exc_type is None:
                raise
            # Never mask the phase's own failure with an evidence-collection error.

    def verify(self, phase: str, *, record_blackholed_attempt: bool = False) -> None:
        """Fail on fetch evidence; optionally record a blackholed attempt instead.

        With `record_blackholed_attempt`, download log lines and connects to the
        loopback blackhole are printed as an observation, not a failure. Cache
        changes and non-loopback connections still fail.
        """
        if self.error is not None:
            raise AssertionError(f"{phase}: socket sampling failed: {self.error}")
        if not any(self.expect_log in line for line in self.journal):
            raise AssertionError(
                f"{phase}: the service journal has no line naming {self.expect_log}; "
                "run with access to the system journal"
            )
        fetch_lines = [line for line in self.journal if FETCH_LOG_RE.search(line)]
        print(f"{phase}_journal_lines", len(self.journal))
        print(f"{phase}_fetch_log_lines", len(fetch_lines))
        if fetch_lines and not record_blackholed_attempt:
            raise AssertionError(f"{phase}: the service logged {len(fetch_lines)} download or install lines")
        if not fetch_lines:
            print(f"{phase}_no_fetch_log_ok")
        for name in self.caches:
            changes = tree_changes(self.before[name], self.after[name])
            print(f"{phase}_{name}_entries", len(self.after[name]), f"changed={len(changes)}")
            if changes:
                raise AssertionError(f"{phase}: {name} changed in {len(changes)} entries")
            print(f"{phase}_{name}_unchanged_ok")
        print(f"{phase}_socket_samples", self.samples)
        print(f"{phase}_remote_connections", len(self.remote))
        print(f"{phase}_blackhole_connects", self.blackhole_hits)
        if self.remote:
            raise AssertionError(f"{phase}: lemond connected to {len(self.remote)} non-loopback peers")
        if self.blackhole_hits and not record_blackholed_attempt:
            raise AssertionError(f"{phase}: lemond connected to the download blackhole")
        if fetch_lines or self.blackhole_hits:
            print(
                f"{phase}_blackholed_fetch_attempt_recorded",
                f"log_lines={len(fetch_lines)}",
                f"blackhole_connects={self.blackhole_hits}",
            )
        print(f"{phase}_no_remote_connection_ok")


def require_socket_attribution(host: ServiceHost) -> None:
    """ss -p must see lemond's own sockets, or an empty sample would prove nothing."""
    tree = host.process_tree(host.main_pid())
    if not any(row["pids"] & tree for row in host.sockets()):
        raise AssertionError(
            "network_attribution_unavailable: ss -p cannot see lemond's sockets; "
            "run with privileges that let ss attribute the service's sockets"
        )
    print("network_attribution_ok")


def run_nofetch(
    client: LemonadeClient,
    *,
    host: ServiceHost,
    model: str,
    missing_model: str,
    backend: str,
    ctx_size: int,
    expect_checkpoint: str | None,
    expect_sha256: str | None,
    repo: str = "strix-halo-gfx1151",
    interval: float = 0.2,
    journal_timeout: float = 10.0,
    text: Callable[..., None] = run_text,
) -> None:
    config = client.get("/internal/config")
    for key in ("offline", "no_fetch_executables"):
        if config.get(key) is not True:
            raise AssertionError(f"service config {key} is {config.get(key)!r}, expected true")
    print("offline_config_ok")
    blackhole = blackhole_ports(host.endpoint_env())
    print("endpoint_blackhole_ok")
    require_socket_attribution(host)

    storage = (client.get("/system-info").get("model_storage") or {}).get("path")
    if not storage:
        raise AssertionError("system-info reports no model_storage path")
    caches = {"model_cache": Path(str(storage)), "backend_cache": host.cache_dir() / "bin"}

    with FetchWatch(
        host, caches=caches, blackhole=blackhole, expect_log=model,
        interval=interval, journal_timeout=journal_timeout,
    ) as watch:
        text(
            client,
            model=model,
            backend=backend,
            ctx_size=ctx_size,
            expect_checkpoint=expect_checkpoint,
            expect_sha256=expect_sha256,
            repo=repo,
            cache_bins=(caches["backend_cache"],),
        )
    watch.verify("preplaced")

    status, payload = client.request("GET", f"/models/{quote_model(missing_model)}", check=False)
    info = payload.get("data", payload) if isinstance(payload, dict) else {}
    if status < 400 and isinstance(info, dict) and info.get("downloaded"):
        raise AssertionError(f"missing_model_present: {missing_model} is downloaded; pick an absent model")
    print("missing_model_absent_ok")
    was_loaded = loaded_entry(client.get("/health"), missing_model) is not None
    with FetchWatch(
        host, caches=caches, blackhole=blackhole, expect_log=missing_model,
        interval=interval, journal_timeout=journal_timeout,
    ) as watch:
        refusal = load_refusal(client, missing_model, ctx_size=ctx_size)
        if refusal is None and not was_loaded:
            client.request("POST", "/unload", {"model_name": missing_model}, check=False)
    print("missing_model_refusal", json.dumps(refusal))
    if refusal is None:
        raise AssertionError(f"loading absent model {missing_model} succeeded; it was fetched")
    if loaded_entry(client.get("/health"), missing_model) is not None:
        raise AssertionError(f"{missing_model} became resident after a refused load")
    print("missing_model_refused_ok")
    # Ruling for candidate 187b4a25f: /load of a registered-but-absent model
    # logs a download attempt even with offline=true. The phase passes when the
    # load fails loudly, the caches are unchanged, and lemond made no
    # non-loopback connection; a logged, blackholed attempt is recorded.
    watch.verify("missing", record_blackholed_attempt=True)
    print("no_fetch_ok")


# --- Consumer pins (service, read-only) --------------------------------------


def parse_expected_pins(values: list[str]) -> list[tuple[str, str]]:
    pins = []
    for value in values:
        model, sep, variant = value.partition("=")
        if not sep or not model or not variant:
            raise SystemExit(f"--expect-pin takes MODEL=VARIANT, got {value!r}")
        pins.append((model, variant))
    return pins


def run_service_pins(client: LemonadeClient, *, expected: list[tuple[str, str]]) -> None:
    if not expected:
        raise SystemExit("service-pins mode requires at least one --expect-pin")
    pins = {str(pin.get("model_name")): pin for pin in client.get("/pins").get("data", [])}
    health = client.get("/health")
    for model, variant in expected:
        pin = pins.get(model)
        if pin is None:
            raise AssertionError(f"{model} is not pinned; pins: {sorted(pins)}")
        if pin.get("load_error"):
            raise AssertionError(f"pinned {model} failed to load: {pin['load_error']}")
        if not pin.get("loaded"):
            raise AssertionError(f"pinned {model} is not loaded")
        entry = loaded_entry(health, model)
        if entry is None or not entry.get("pinned"):
            raise AssertionError(f"{model} is not resident as pinned in /health")
        checkpoint = main_checkpoint(model_info(client, model)) or ""
        quant = checkpoint.rpartition(":")[2]
        if variant.lower() not in quant.lower():
            raise AssertionError(f"{model} checkpoint {checkpoint!r} is not the {variant} variant")
        print("service_pin", model, checkpoint)
    print("service_pins_ok")


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
    parser.add_argument("--expect-checkpoint", help="exact main checkpoint the text model must use")
    parser.add_argument("--expect-sha256", help="required SHA-256 of the exercised GGUF file")
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
    parser.add_argument("--missing-model", default="Tiny-Test-Model-GGUF", help="absent model for nofetch mode")
    parser.add_argument(
        "--expect-pin", action="append", default=[], help="MODEL=VARIANT that service-pins mode requires"
    )
    parser.add_argument("--stream-tokens", type=int, default=2048)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--request-timeout", type=float, default=600.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    print("mode", args.mode)
    if args.mode in SERVICE_MODES:
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
                expect_sha256=args.expect_sha256,
                repo=args.repo,
                cache_bins=(ServiceHost(args.service).cache_dir() / "bin",),
            )
        elif args.mode == "nofetch":
            if not args.model:
                raise SystemExit("nofetch mode requires --model")
            run_nofetch(
                client,
                host=ServiceHost(args.service),
                model=args.model,
                missing_model=args.missing_model,
                backend=args.backend,
                ctx_size=args.ctx_size,
                expect_checkpoint=args.expect_checkpoint,
                expect_sha256=args.expect_sha256,
                repo=args.repo,
            )
        elif args.mode == "service-pins":
            run_service_pins(client, expected=parse_expected_pins(args.expect_pin))
        else:
            run_provenance(client, repo=args.repo, service=args.service)
        return

    needs_gguf = args.mode != "lifecycle"
    if needs_gguf and (args.gguf is None or not args.gguf.is_file()):
        raise SystemExit(f"{args.mode} mode requires --gguf pointing at a local GGUF file")
    if needs_gguf:
        verify_sha256(args.gguf, args.expect_sha256)
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
