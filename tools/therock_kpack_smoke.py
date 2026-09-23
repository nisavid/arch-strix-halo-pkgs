#!/usr/bin/env python3
"""Installed smoke for the TheRock gfx1151 split family and its kpack archives.

TheRock 7.14.1 ships kpack-split libraries: their gfx1151 kernels live in
``/opt/rocm/.kpack/<family>_gfx1151.kpack`` rather than in the library. A
render, build, or install that drops an archive still passes, and the first
kernel launch fails. This tool launches at least one real kernel per archive
family, so it proves each archive is present and loadable.

Two subcommands:

``probe``
    Run GPU probes against a ROCm tree (``/opt/rocm`` by default). Each probe
    runs in its own child process. ``--sandbox-root <root>`` runs the probes
    rootless in bubblewrap, with ``<root>/opt/rocm`` bound over ``/opt/rocm``,
    so staged packages extracted into ``<root>`` can be checked without
    installing them. ``--sandbox-python`` also binds the staged CPython from
    ``<root>/usr`` over the host interpreter, keeping the host site-packages.

``check-packages``
    Check built package archives: no path is owned by two packages, the
    extracted root matches the union of the package file lists, and every
    kpack-split ELF reaches an archive owned by its package or a direct depend.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROCM = Path("/opt/rocm")
DEFAULT_ARCH = "gfx1151"
PROBE_TIMEOUT_SECONDS = 600

# Archive family -> probes that launch a kernel from that archive.
KPACK_FAMILY_PROBES: dict[str, tuple[str, ...]] = {
    "rand_lib": ("rocrand",),
    "blas_lib": ("rocblas", "rocsolver"),
    "fft_lib": ("rocfft-callback",),
    "rccl_lib": ("rccl",),
    "hiptensor_lib": ("hiptensor",),
    "rocalution_lib": ("rocalution",),
}
DEFAULT_PROBES = (
    "hip",
    "rocrand",
    "rocblas",
    "rocsolver",
    "rocfft",
    "rocfft-callback",
    "rccl",
    "hiptensor",
    "rocalution",
)
OPTIONAL_PROBES = ("migraphx",)
ALL_PROBES = DEFAULT_PROBES + OPTIONAL_PROBES


@dataclass(frozen=True)
class KnownGap:
    """An upstream defect that makes a probe fail with a recognizable signature.

    A matching failure is reported as XFAIL and does not fail the run; any
    other failure of the probe still does. A pass is reported as XPASS so the
    gap can be retired.
    """

    signature: str
    note: str


KNOWN_GAPS: dict[str, KnownGap] = {
    "rocfft-callback": KnownGap(
        signature=r"Cannot create GlobalVar Obj for symbol: _ZL\d+(load|store)_cb_default",
        note=(
            "ROCm/TheRock#5444: the fft_lib kpack code object names rocFFT's static default "
            "callbacks with a different .static hash than librocfft registers, so a plan "
            "with a user callback aborts"
        ),
    ),
}


def probe_family(probe: str) -> str | None:
    for family, probes in KPACK_FAMILY_PROBES.items():
        if probe in probes:
            return family
    return None


def archive_family(name: str, arch: str) -> str | None:
    suffix = f"_{arch}.kpack"
    return name[: -len(suffix)] if name.endswith(suffix) else None


def classify(result: dict) -> str:
    """Return PASS, FAIL, XFAIL (known gap, matching signature), or XPASS."""
    gap = KNOWN_GAPS.get(result["probe"])
    if result.get("ok"):
        return "XPASS" if gap else "PASS"
    text = f"{result.get('error', '')}\n{result.get('stderr_tail', '')}"
    if gap and re.search(gap.signature, text):
        return "XFAIL"
    return "FAIL"


def kpack_coverage(archives: list[str], results: list[dict], arch: str) -> dict:
    """Map each staged archive family to the probes that exercised it.

    A family counts as covered by a passing probe, or by a known-gap probe
    that failed with the gap's signature (the archive loaded; its content is
    what upstream got wrong).
    """
    status = {result["probe"]: classify(result) for result in results}
    families = sorted(
        {family for name in archives if (family := archive_family(name, arch))}
    )
    covered = {
        family: sorted(
            probe
            for probe in KPACK_FAMILY_PROBES.get(family, ())
            if status.get(probe) in ("PASS", "XPASS")
        )
        for family in families
    }
    gapped = {
        family: sorted(
            probe
            for probe in KPACK_FAMILY_PROBES.get(family, ())
            if status.get(probe) == "XFAIL"
        )
        for family in families
    }
    return {
        "families": families,
        "covered": covered,
        "known_gap": {
            family: probes
            for family, probes in gapped.items()
            if probes and not covered[family]
        },
        "uncovered": sorted(
            family for family in families if not covered[family] and not gapped[family]
        ),
        "unknown_families": sorted(
            family for family in families if family not in KPACK_FAMILY_PROBES
        ),
        "missing_archives": sorted(
            family for family in KPACK_FAMILY_PROBES if family not in families
        ),
    }


# --------------------------------------------------------------------------
# Probe helpers (run in the child process)
# --------------------------------------------------------------------------


class ProbeFailure(RuntimeError):
    pass


def check(rc: int, what: str) -> None:
    if rc != 0:
        raise ProbeFailure(f"{what} returned {rc}")


class Hip:
    HOST_TO_DEVICE = 1
    DEVICE_TO_HOST = 2

    def __init__(self, lib_dir: Path) -> None:
        self.lib = ctypes.CDLL(str(lib_dir / "libamdhip64.so.7"))
        self.allocations: list[ctypes.c_void_p] = []

    def malloc(self, nbytes: int) -> ctypes.c_void_p:
        ptr = ctypes.c_void_p()
        check(
            self.lib.hipMalloc(ctypes.byref(ptr), ctypes.c_size_t(nbytes)), "hipMalloc"
        )
        self.allocations.append(ptr)
        return ptr

    def upload(self, values: list[float], ctype=ctypes.c_float) -> ctypes.c_void_p:
        host = (ctype * len(values))(*values)
        ptr = self.malloc(ctypes.sizeof(host))
        check(
            self.lib.hipMemcpy(
                ptr, host, ctypes.c_size_t(ctypes.sizeof(host)), self.HOST_TO_DEVICE
            ),
            "hipMemcpy H2D",
        )
        return ptr

    def download(self, ptr: ctypes.c_void_p, count: int, ctype=ctypes.c_float) -> list:
        host = (ctype * count)()
        check(
            self.lib.hipMemcpy(
                host, ptr, ctypes.c_size_t(ctypes.sizeof(host)), self.DEVICE_TO_HOST
            ),
            "hipMemcpy D2H",
        )
        return list(host)

    def sync(self) -> None:
        check(self.lib.hipDeviceSynchronize(), "hipDeviceSynchronize")

    def free_all(self) -> None:
        for ptr in self.allocations:
            self.lib.hipFree(ptr)
        self.allocations.clear()


def matmul_colmajor(
    a: list[float], b: list[float], m: int, n: int, k: int
) -> list[float]:
    return [
        sum(a[i + p * m] * b[p + j * k] for p in range(k))
        for j in range(n)
        for i in range(m)
    ]


def max_abs_diff(left: list[float], right: list[float]) -> float:
    return max(abs(x - y) for x, y in zip(left, right, strict=True))


def probe_hip(lib_dir: Path, arch: str, workdir: Path) -> dict:
    hip = Hip(lib_dir)
    count = ctypes.c_int()
    check(hip.lib.hipGetDeviceCount(ctypes.byref(count)), "hipGetDeviceCount")
    version = ctypes.c_int()
    check(hip.lib.hipRuntimeGetVersion(ctypes.byref(version)), "hipRuntimeGetVersion")
    devices = []
    for index in range(count.value):
        # hipDeviceProp_t is large and version-specific; name is its first
        # field and gcnArchName is the only "gfx..." string in it.
        props = ctypes.create_string_buffer(16384)
        check(
            hip.lib.hipGetDevicePropertiesR0600(props, index),
            "hipGetDevicePropertiesR0600",
        )
        names = re.findall(rb"gfx[0-9a-f]+[^\x00]*", props.raw)
        devices.append(
            {
                "name": props.raw.split(b"\0", 1)[0].decode(errors="replace"),
                "gcn_arch": names[0].decode(errors="replace") if names else None,
            }
        )
    archs = [
        device["gcn_arch"].split(":", 1)[0] for device in devices if device["gcn_arch"]
    ]
    if arch not in archs:
        raise ProbeFailure(f"no {arch} device among {archs or 'no devices'}")
    return {"runtime_version": version.value, "devices": devices}


def probe_rocrand(lib_dir: Path, arch: str, workdir: Path) -> dict:
    hip = Hip(lib_dir)
    rocrand = ctypes.CDLL(str(lib_dir / "librocrand.so.1"))
    count = 1 << 16
    out = hip.malloc(count * 4)
    generator = ctypes.c_void_p()
    rng_xorwow = 401
    check(
        rocrand.rocrand_create_generator(ctypes.byref(generator), rng_xorwow),
        "rocrand_create_generator",
    )
    check(
        rocrand.rocrand_generate_uniform(generator, out, ctypes.c_size_t(count)),
        "rocrand_generate_uniform",
    )
    hip.sync()
    values = hip.download(out, count)
    rocrand.rocrand_destroy_generator(generator)
    hip.free_all()
    mean = sum(values) / count
    if not all(0.0 < value <= 1.0 for value in values) or abs(mean - 0.5) > 0.01:
        raise ProbeFailure(
            f"generate_uniform output is not uniform on (0, 1]: mean {mean:.4f}"
        )
    return {"count": count, "mean": round(mean, 4)}


ROCBLAS_OPERATION_NONE = 111


def probe_rocblas(lib_dir: Path, arch: str, workdir: Path) -> dict:
    hip = Hip(lib_dir)
    rocblas = ctypes.CDLL(str(lib_dir / "librocblas.so.5"))
    handle = ctypes.c_void_p()
    check(rocblas.rocblas_create_handle(ctypes.byref(handle)), "rocblas_create_handle")
    m, n, k = 16, 12, 8
    a = [((i * 7) % 11 - 5) / 4 for i in range(m * k)]
    b = [((i * 5) % 13 - 6) / 3 for i in range(k * n)]
    d_a, d_b, d_c = hip.upload(a), hip.upload(b), hip.malloc(m * n * 4)
    alpha, beta = ctypes.c_float(1.0), ctypes.c_float(0.0)
    check(
        rocblas.rocblas_sgemm(
            handle,
            ROCBLAS_OPERATION_NONE,
            ROCBLAS_OPERATION_NONE,
            m,
            n,
            k,
            ctypes.byref(alpha),
            d_a,
            m,
            d_b,
            k,
            ctypes.byref(beta),
            d_c,
            m,
        ),
        "rocblas_sgemm",
    )
    x = [float(i % 9) for i in range(256)]
    d_x = hip.upload(x)
    scale = ctypes.c_float(2.5)
    check(
        rocblas.rocblas_sscal(handle, len(x), ctypes.byref(scale), d_x, 1),
        "rocblas_sscal",
    )
    hip.sync()
    gemm_err = max_abs_diff(hip.download(d_c, m * n), matmul_colmajor(a, b, m, n, k))
    scal_err = max_abs_diff(hip.download(d_x, len(x)), [2.5 * value for value in x])
    rocblas.rocblas_destroy_handle(handle)
    hip.free_all()
    if gemm_err > 1e-3 or scal_err > 1e-5:
        raise ProbeFailure(f"sgemm max error {gemm_err}, sscal max error {scal_err}")
    return {
        "sgemm": f"{m}x{n}x{k}",
        "sgemm_max_err": gemm_err,
        "sscal_max_err": scal_err,
    }


def probe_rocsolver(lib_dir: Path, arch: str, workdir: Path) -> dict:
    hip = Hip(lib_dir)
    rocblas = ctypes.CDLL(str(lib_dir / "librocblas.so.5"))
    rocsolver = ctypes.CDLL(str(lib_dir / "librocsolver.so.0"))
    handle = ctypes.c_void_p()
    check(rocblas.rocblas_create_handle(ctypes.byref(handle)), "rocblas_create_handle")
    n = 8
    # Diagonally dominant, so getrf needs no heroic pivoting.
    a = [
        (float(n + 2) if i == j else ((i * 3 + j * 5) % 7 - 3) / 4)
        for j in range(n)
        for i in range(n)
    ]
    x_true = [float(i + 1) for i in range(n)]
    b = [sum(a[i + j * n] * x_true[j] for j in range(n)) for i in range(n)]
    d_a, d_b = hip.upload(a), hip.upload(b)
    d_ipiv = hip.malloc(n * 4)
    d_info = hip.malloc(4)
    check(
        rocsolver.rocsolver_sgetrf(handle, n, n, d_a, n, d_ipiv, d_info),
        "rocsolver_sgetrf",
    )
    check(
        rocsolver.rocsolver_sgetrs(
            handle, ROCBLAS_OPERATION_NONE, n, 1, d_a, n, d_ipiv, d_b, n
        ),
        "rocsolver_sgetrs",
    )
    hip.sync()
    info = hip.download(d_info, 1, ctypes.c_int)[0]
    err = max_abs_diff(hip.download(d_b, n), x_true)
    rocblas.rocblas_destroy_handle(handle)
    hip.free_all()
    if info != 0 or err > 1e-3:
        raise ProbeFailure(f"getrf info {info}, solve max error {err}")
    return {"getrf_getrs": f"{n}x{n}", "max_err": err}


ROCFFT_LOAD_CALLBACK_SOURCE = """
extern "C" __device__ float2 ashp_load_times_two(float2* buffer, size_t offset, void* data, void* shared)
{
    float2 value = buffer[offset];
    return make_float2(2.0f * value.x, 2.0f * value.y);
}
extern "C" __device__ void* ashp_load_times_two_ptr = (void*)ashp_load_times_two;
"""


def device_function_pointer(
    hip: Hip, lib_dir: Path, arch: str, source: str, symbol: str
) -> tuple[int, ctypes.c_void_p]:
    """Compile ``source`` with hipRTC and return the device address stored in ``symbol``."""
    hiprtc = ctypes.CDLL(str(lib_dir / "libhiprtc.so.7"))
    program = ctypes.c_void_p()
    check(
        hiprtc.hiprtcCreateProgram(
            ctypes.byref(program), source.encode(), b"ashp_callback.hip", 0, None, None
        ),
        "hiprtcCreateProgram",
    )
    options = (ctypes.c_char_p * 1)(f"--offload-arch={arch}".encode())
    rc = hiprtc.hiprtcCompileProgram(program, 1, options)
    if rc != 0:
        log_size = ctypes.c_size_t()
        hiprtc.hiprtcGetProgramLogSize(program, ctypes.byref(log_size))
        log = ctypes.create_string_buffer(log_size.value or 1)
        hiprtc.hiprtcGetProgramLog(program, log)
        raise ProbeFailure(
            f"hiprtcCompileProgram returned {rc}: {log.value.decode(errors='replace')[-1500:]}"
        )
    code_size = ctypes.c_size_t()
    check(
        hiprtc.hiprtcGetCodeSize(program, ctypes.byref(code_size)), "hiprtcGetCodeSize"
    )
    code = ctypes.create_string_buffer(code_size.value)
    check(hiprtc.hiprtcGetCode(program, code), "hiprtcGetCode")
    hiprtc.hiprtcDestroyProgram(ctypes.byref(program))
    module = ctypes.c_void_p()
    check(hip.lib.hipModuleLoadData(ctypes.byref(module), code), "hipModuleLoadData")
    global_ptr, global_size = ctypes.c_void_p(), ctypes.c_size_t()
    check(
        hip.lib.hipModuleGetGlobal(
            ctypes.byref(global_ptr), ctypes.byref(global_size), module, symbol.encode()
        ),
        "hipModuleGetGlobal",
    )
    address = ctypes.c_uint64()
    check(
        hip.lib.hipMemcpy(
            ctypes.byref(address), global_ptr, ctypes.c_size_t(8), Hip.DEVICE_TO_HOST
        ),
        "hipMemcpy callback pointer",
    )
    return address.value, module


def run_rocfft(
    lib_dir: Path, arch: str, workdir: Path, *, load_callback: bool
) -> float:
    """Run a length-16 forward C2C FFT and return its max error.

    With ``load_callback`` the plan runs with a hipRTC load callback that
    doubles the input, so rocFFT takes its default store callback from the
    library's device code.
    """
    os.environ.setdefault(
        "ROCFFT_RTC_CACHE_PATH", str(workdir / "rocfft_kernel_cache.db")
    )
    hip = Hip(lib_dir)
    rocfft = ctypes.CDLL(str(lib_dir / "librocfft.so.0"))
    check(rocfft.rocfft_setup(), "rocfft_setup")
    length = 16
    signal = [
        complex(math.cos(0.3 * t) + 0.25 * (t % 3), math.sin(0.7 * t))
        for t in range(length)
    ]
    interleaved = [part for value in signal for part in (value.real, value.imag)]
    scale = 2.0 if load_callback else 1.0
    expected = [
        scale
        * sum(
            signal[t]
            * complex(
                math.cos(-2 * math.pi * f * t / length),
                math.sin(-2 * math.pi * f * t / length),
            )
            for t in range(length)
        )
        for f in range(length)
    ]
    plan = ctypes.c_void_p()
    lengths = (ctypes.c_size_t * 1)(length)
    placement_inplace, forward_complex, single = 0, 0, 0
    check(
        rocfft.rocfft_plan_create(
            ctypes.byref(plan),
            placement_inplace,
            forward_complex,
            single,
            ctypes.c_size_t(1),
            lengths,
            ctypes.c_size_t(1),
            None,
        ),
        "rocfft_plan_create",
    )
    info = ctypes.c_void_p()
    check(
        rocfft.rocfft_execution_info_create(ctypes.byref(info)),
        "rocfft_execution_info_create",
    )
    work_size = ctypes.c_size_t()
    check(
        rocfft.rocfft_plan_get_work_buffer_size(plan, ctypes.byref(work_size)),
        "rocfft_plan_get_work_buffer_size",
    )
    if work_size.value:
        check(
            rocfft.rocfft_execution_info_set_work_buffer(
                info, hip.malloc(work_size.value), work_size
            ),
            "rocfft_execution_info_set_work_buffer",
        )
    module = None
    if load_callback:
        address, module = device_function_pointer(
            hip, lib_dir, arch, ROCFFT_LOAD_CALLBACK_SOURCE, "ashp_load_times_two_ptr"
        )
        functions = (ctypes.c_void_p * 1)(address)
        data = (ctypes.c_void_p * 1)(None)
        check(
            rocfft.rocfft_execution_info_set_load_callback(
                info, functions, data, ctypes.c_size_t(0)
            ),
            "rocfft_execution_info_set_load_callback",
        )
    d_buf = hip.upload(interleaved)
    buffers = (ctypes.c_void_p * 1)(d_buf)
    check(rocfft.rocfft_execute(plan, buffers, None, info), "rocfft_execute")
    hip.sync()
    raw = hip.download(d_buf, 2 * length)
    result = [complex(raw[2 * i], raw[2 * i + 1]) for i in range(length)]
    rocfft.rocfft_execution_info_destroy(info)
    rocfft.rocfft_plan_destroy(plan)
    rocfft.rocfft_cleanup()
    if module is not None:
        hip.lib.hipModuleUnload(module)
    hip.free_all()
    return max(abs(x - y) for x, y in zip(result, expected, strict=True))


def probe_rocfft(lib_dir: Path, arch: str, workdir: Path) -> dict:
    # rocFFT builds FFT kernels at runtime (RTC), so this does not touch fft_lib.
    err = run_rocfft(lib_dir, arch, workdir, load_callback=False)
    if err > 1e-3:
        raise ProbeFailure(f"forward FFT max error {err}")
    return {"fft": "c2c forward, length 16, RTC kernels", "max_err": err}


def probe_rocfft_callback(lib_dir: Path, arch: str, workdir: Path) -> dict:
    # fft_lib holds only rocFFT's default load/store callbacks, which rocFFT
    # reads only when a plan runs with a user callback.
    err = run_rocfft(lib_dir, arch, workdir, load_callback=True)
    if err > 2e-3:
        raise ProbeFailure(f"forward FFT with load callback max error {err}")
    return {
        "fft": "c2c forward, length 16, hipRTC load callback x2, default store callback",
        "max_err": err,
    }


NCCL_FLOAT = 7
NCCL_SCALAR_HOST_IMMEDIATE = 1


def probe_rccl(lib_dir: Path, arch: str, workdir: Path) -> dict:
    os.environ.setdefault("NCCL_DEBUG", "WARN")
    hip = Hip(lib_dir)
    rccl = ctypes.CDLL(str(lib_dir / "librccl.so.1"))
    comms = (ctypes.c_void_p * 1)()
    devices = (ctypes.c_int * 1)(0)
    check(rccl.ncclCommInitAll(comms, 1, devices), "ncclCommInitAll")
    comm = ctypes.c_void_p(comms[0])
    count = 1024
    send = [float(i % 17) for i in range(count)]
    d_send, d_recv = hip.upload(send), hip.malloc(count * 4)
    # A one-rank sum could be a plain copy. Pre-multiplying by 2 needs a kernel.
    op = ctypes.c_int()
    scalar = ctypes.c_float(2.0)
    check(
        rccl.ncclRedOpCreatePreMulSum(
            ctypes.byref(op),
            ctypes.byref(scalar),
            NCCL_FLOAT,
            NCCL_SCALAR_HOST_IMMEDIATE,
            comm,
        ),
        "ncclRedOpCreatePreMulSum",
    )
    check(
        rccl.ncclAllReduce(
            d_send, d_recv, ctypes.c_size_t(count), NCCL_FLOAT, op, comm, None
        ),
        "ncclAllReduce",
    )
    hip.sync()
    err = max_abs_diff(hip.download(d_recv, count), [2.0 * value for value in send])
    rccl.ncclRedOpDestroy(op, comm)
    rccl.ncclCommDestroy(comm)
    hip.free_all()
    if err > 1e-5:
        raise ProbeFailure(f"premulsum allreduce max error {err}")
    return {"allreduce": f"1 rank, premulsum x2, {count} floats", "max_err": err}


HIPTENSOR_R_32F = 0
HIPTENSOR_OP_IDENTITY = 1
HIPTENSOR_COMPUTE_DESC_32F = 1 << 2
HIPTENSOR_ALGO_DEFAULT = -1
HIPTENSOR_JIT_MODE_NONE = 0
HIPTENSOR_WORKSPACE_DEFAULT = 2


HIPTENSOR_STATUS_ARCH_MISMATCH = 8


def probe_hiptensor(lib_dir: Path, arch: str, workdir: Path) -> dict:
    hip = Hip(lib_dir)
    ht = ctypes.CDLL(str(lib_dir / "libhiptensor.so.0"))
    handle = ctypes.c_void_p()
    check(ht.hiptensorCreate(ctypes.byref(handle)), "hiptensorCreate")
    created: list[ctypes.c_void_p] = []

    def descriptor(*lens: int) -> ctypes.c_void_p:
        desc = ctypes.c_void_p()
        extents = (ctypes.c_int64 * len(lens))(*lens)
        check(
            ht.hiptensorCreateTensorDescriptor(
                handle,
                ctypes.byref(desc),
                len(lens),
                extents,
                None,
                HIPTENSOR_R_32F,
                128,
            ),
            "hiptensorCreateTensorDescriptor",
        )
        created.append(desc)
        return desc

    def modes(*names: str):
        return (ctypes.c_int32 * len(names))(*(ord(name) for name in names))

    def plan_for(
        op: ctypes.c_void_p,
    ) -> tuple[ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]:
        pref = ctypes.c_void_p()
        check(
            ht.hiptensorCreatePlanPreference(
                handle,
                ctypes.byref(pref),
                HIPTENSOR_ALGO_DEFAULT,
                HIPTENSOR_JIT_MODE_NONE,
            ),
            "hiptensorCreatePlanPreference",
        )
        workspace_size = ctypes.c_uint64()
        check(
            ht.hiptensorEstimateWorkspaceSize(
                handle,
                op,
                pref,
                HIPTENSOR_WORKSPACE_DEFAULT,
                ctypes.byref(workspace_size),
            ),
            "hiptensorEstimateWorkspaceSize",
        )
        plan = ctypes.c_void_p()
        check(
            ht.hiptensorCreatePlan(
                handle, ctypes.byref(plan), op, pref, workspace_size
            ),
            "hiptensorCreatePlan",
        )
        ht.hiptensorDestroyPlanPreference(pref)
        return (
            plan,
            (hip.malloc(workspace_size.value) if workspace_size.value else None),
            workspace_size,
        )

    # Permutation: B[n,m] = 2 * A[m,n]. This is the kernel the probe requires.
    m, n = 8, 16
    a = [((i * 7) % 11 - 5) / 4 for i in range(m * n)]
    d_a, d_b = hip.upload(a), hip.malloc(m * n * 4)
    permute = ctypes.c_void_p()
    check(
        ht.hiptensorCreatePermutation(
            handle,
            ctypes.byref(permute),
            descriptor(m, n),
            modes("m", "n"),
            HIPTENSOR_OP_IDENTITY,
            descriptor(n, m),
            modes("n", "m"),
            ctypes.c_uint(HIPTENSOR_COMPUTE_DESC_32F),
        ),
        "hiptensorCreatePermutation",
    )
    plan, _workspace, _size = plan_for(permute)
    alpha = ctypes.c_float(2.0)
    check(
        ht.hiptensorPermute(handle, plan, ctypes.byref(alpha), d_a, d_b, None),
        "hiptensorPermute",
    )
    hip.sync()
    # Column-major: A(i, j) = a[i + j*m]; B(j, i) = b[j + i*n].
    expected = [2.0 * a[i + j * m] for i in range(m) for j in range(n)]
    err = max_abs_diff(hip.download(d_b, m * n), expected)
    ht.hiptensorDestroyPlan(plan)
    ht.hiptensorDestroyOperationDescriptor(permute)
    detail = {"permutation": f"f32 mn->nm {m}x{n}, alpha 2", "max_err": err}

    # Contraction is informational: hipTensor has no gfx11 contraction kernels.
    k = 8
    b = [((i * 5) % 13 - 6) / 3 for i in range(k * n)]
    contraction = ctypes.c_void_p()
    rc = ht.hiptensorCreateContraction(
        handle,
        ctypes.byref(contraction),
        descriptor(m, k),
        modes("m", "k"),
        HIPTENSOR_OP_IDENTITY,
        descriptor(k, n),
        modes("k", "n"),
        HIPTENSOR_OP_IDENTITY,
        descriptor(m, n),
        modes("m", "n"),
        HIPTENSOR_OP_IDENTITY,
        created[-1],
        modes("m", "n"),
        ctypes.c_uint(HIPTENSOR_COMPUTE_DESC_32F),
    )
    if rc == HIPTENSOR_STATUS_ARCH_MISMATCH:
        detail["contraction"] = (
            f"unsupported on {arch} (HIPTENSOR_STATUS_ARCH_MISMATCH)"
        )
    elif rc != 0:
        detail["contraction"] = f"hiptensorCreateContraction returned {rc}"
    else:
        d_ka, d_kb, d_kd = hip.upload(a[: m * k]), hip.upload(b), hip.malloc(m * n * 4)
        cplan, workspace, workspace_size = plan_for(contraction)
        one, zero = ctypes.c_float(1.0), ctypes.c_float(0.0)
        check(
            ht.hiptensorContract(
                handle,
                cplan,
                ctypes.byref(one),
                d_ka,
                d_kb,
                ctypes.byref(zero),
                d_kd,
                d_kd,
                workspace,
                workspace_size,
                None,
            ),
            "hiptensorContract",
        )
        hip.sync()
        detail["contraction_max_err"] = max_abs_diff(
            hip.download(d_kd, m * n), matmul_colmajor(a[: m * k], b, m, n, k)
        )
        ht.hiptensorDestroyPlan(cplan)
        ht.hiptensorDestroyOperationDescriptor(contraction)
    for desc in created:
        ht.hiptensorDestroyTensorDescriptor(desc)
    ht.hiptensorDestroy(handle)
    hip.free_all()
    if err > 1e-5 or detail.get("contraction_max_err", 0.0) > 1e-3:
        raise ProbeFailure(f"hipTensor results are wrong: {detail}")
    return detail


ROCALUTION_SOURCE = r"""
#include <rocalution/rocalution.hpp>
#include <cmath>
#include <cstdio>

using namespace rocalution;

int main()
{
    init_rocalution();
    if(!_rocalution_available_accelerator())
    {
        std::printf("no accelerator\n");
        stop_rocalution();
        return 2;
    }
    const int n = 64;
    LocalMatrix<float> mat;
    LocalVector<float> x, y;
    int*   row = new int[n + 1];
    int*   col = new int[n];
    float* val = new float[n];
    for(int i = 0; i < n; ++i)
    {
        row[i] = i;
        col[i] = i;
        val[i] = 2.0f;
    }
    row[n] = n;
    mat.SetDataPtrCSR(&row, &col, &val, "A", n, n, n);
    x.Allocate("x", n);
    y.Allocate("y", n);
    x.Ones();
    mat.MoveToAccelerator();
    x.MoveToAccelerator();
    y.MoveToAccelerator();
    mat.Apply(x, &y);
    x.Scale(3.0f);
    const float spmv = y.Reduce();
    const float scaled = x.Reduce();
    std::printf("spmv_sum=%g scale_sum=%g\n", static_cast<double>(spmv), static_cast<double>(scaled));
    stop_rocalution();
    return (std::fabs(spmv - 2.0f * n) < 1e-3f && std::fabs(scaled - 3.0f * n) < 1e-3f) ? 0 : 1;
}
"""


def probe_rocalution(lib_dir: Path, arch: str, workdir: Path) -> dict:
    # rocALUTION has only a C++ API, so this probe compiles a tiny host program.
    compiler = (
        os.environ.get("CXX")
        or shutil.which("c++")
        or shutil.which("g++")
        or shutil.which("clang++")
    )
    if not compiler:
        raise ProbeFailure("rocALUTION probe needs a host C++ compiler (set CXX)")
    include_dir = lib_dir.parent / "include"
    source = workdir / "rocalution_probe.cpp"
    binary = workdir / "rocalution_probe"
    source.write_text(ROCALUTION_SOURCE)
    compile_cmd = [
        compiler,
        "-std=c++17",
        "-O1",
        "-D__HIP_PLATFORM_AMD__",
        f"-I{include_dir}",
        str(source),
        f"-L{lib_dir}",
        "-lrocalution",
        f"-Wl,-rpath,{lib_dir}",
        "-o",
        str(binary),
    ]
    built = subprocess.run(compile_cmd, capture_output=True, text=True, check=False)
    if built.returncode:
        raise ProbeFailure(f"compile failed: {built.stderr.strip()[-2000:]}")
    ran = subprocess.run(
        [str(binary)],
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_SECONDS,
        check=False,
    )
    output = (ran.stdout + ran.stderr).strip()
    if ran.returncode:
        raise ProbeFailure(f"exit {ran.returncode}: {output[-2000:]}")
    return {"spmv_and_scale": output.splitlines()[-1]}


def probe_migraphx(lib_dir: Path, arch: str, workdir: Path) -> dict:
    sys.path.insert(0, str(lib_dir))
    import migraphx
    import numpy as np
    import onnx
    from onnx import TensorProto, helper

    tensors = [
        helper.make_tensor_value_info(name, TensorProto.FLOAT, [2, 3])
        for name in ("x", "y", "z")
    ]
    graph = helper.make_graph(
        [
            helper.make_node("Add", ["x", "y"], ["s"]),
            helper.make_node("Relu", ["s"], ["z"]),
        ],
        "tiny",
        tensors[:2],
        tensors[2:],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    path = workdir / "tiny.onnx"
    onnx.save(model, path)
    a = np.array([[1, -2, 3], [-4, 5, -6]], dtype=np.float32)
    b = np.array([[0.5, 1, -4], [1, -6, 7]], dtype=np.float32)
    expected = np.maximum(a + b, 0)
    detail = {"python": sys.version.split()[0], "module": migraphx.__file__}
    for target in ("ref", "gpu"):
        program = migraphx.parse_onnx(str(path))
        program.compile(migraphx.get_target(target))
        out = np.array(
            program.run({"x": migraphx.argument(a), "y": migraphx.argument(b)})[0]
        ).reshape(expected.shape)
        if not np.allclose(out, expected):
            raise ProbeFailure(
                f"{target} target result {out.tolist()} != {expected.tolist()}"
            )
        detail[f"{target}_target"] = "ok"
    return detail


PROBE_FUNCTIONS = {
    "hip": probe_hip,
    "rocrand": probe_rocrand,
    "rocblas": probe_rocblas,
    "rocsolver": probe_rocsolver,
    "rocfft": probe_rocfft,
    "rocfft-callback": probe_rocfft_callback,
    "rccl": probe_rccl,
    "hiptensor": probe_hiptensor,
    "rocalution": probe_rocalution,
    "migraphx": probe_migraphx,
}


def run_probe_in_process(name: str, rocm: Path, arch: str, workdir: Path) -> dict:
    result: dict = {"probe": name, "family": probe_family(name)}
    try:
        result["detail"] = PROBE_FUNCTIONS[name](rocm / "lib", arch, workdir)
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - every failure becomes a result row
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


# --------------------------------------------------------------------------
# Parent orchestration
# --------------------------------------------------------------------------


def child_env(rocm: Path, extra_lib_dirs: list[Path]) -> dict[str, str]:
    env = dict(os.environ)
    lib_path = [str(rocm / "lib"), *map(str, extra_lib_dirs)]
    if env.get("LD_LIBRARY_PATH"):
        lib_path.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = ":".join(lib_path)
    env["ROCM_PATH"] = str(rocm)
    return env


def run_probe_child(
    name: str, rocm: Path, arch: str, workdir: Path, extra_lib_dirs: list[Path]
) -> dict:
    probe_dir = workdir / name
    probe_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "run-probe",
        name,
        "--rocm",
        str(rocm),
        "--arch",
        arch,
        "--workdir",
        str(probe_dir),
    ]
    try:
        done = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=child_env(rocm, extra_lib_dirs),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "probe": name,
            "family": probe_family(name),
            "ok": False,
            "error": f"timed out after {PROBE_TIMEOUT_SECONDS}s",
        }
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("{"):
            result = json.loads(line)
            if not result.get("ok") and done.stderr.strip():
                result["stderr_tail"] = done.stderr.strip()[-1500:]
            return result
    return {
        "probe": name,
        "family": probe_family(name),
        "ok": False,
        "error": f"child exited {done.returncode} without a result",
        "stderr_tail": done.stderr.strip()[-1500:],
    }


def bwrap_command(
    root: Path,
    workdir: Path,
    inner: list[str],
    *,
    sandbox_python: bool = False,
    host_site_packages: Path = Path("/usr/lib/python3.14/site-packages"),
    extra_binds: list[Path] | None = None,
) -> list[str]:
    """Build a rootless bubblewrap command that overlays a staged root.

    The host filesystem is read-only, the GPU device nodes are passed through,
    ``<root>/opt/rocm`` replaces ``/opt/rocm``, and ``/tmp`` is a writable
    directory under ``workdir`` (comgr needs a writable temp dir to build the
    HIP blit kernels).
    """
    tmp = workdir / "tmp"
    cmd = [
        "bwrap",
        "--die-with-parent",
        "--unshare-pid",
        "--ro-bind",
        "/",
        "/",
        "--dev-bind",
        "/dev",
        "/dev",
        "--proc",
        "/proc",
        "--ro-bind",
        str(root / "opt/rocm"),
        "/opt/rocm",
    ]
    if sandbox_python:
        cmd += [
            "--ro-bind",
            str(root / "usr/bin/python3.14"),
            "/usr/bin/python3.14",
            "--ro-bind",
            str(root / "usr/lib/libpython3.14.so.1.0"),
            "/usr/lib/libpython3.14.so.1.0",
            "--ro-bind",
            str(root / "usr/lib/python3.14"),
            "/usr/lib/python3.14",
            # Keep the host's third-party modules (numpy, onnx) importable.
            "--ro-bind",
            str(host_site_packages),
            "/usr/lib/python3.14/site-packages",
        ]
    for path in extra_binds or []:
        cmd += ["--ro-bind", str(path), str(path)]
    cmd += [
        "--bind",
        str(workdir),
        str(workdir),
        "--bind",
        str(tmp),
        "/tmp",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--chdir",
        str(workdir),
        "--",
        *inner,
    ]
    return cmd


def summarize(results: list[dict], coverage: dict | None) -> tuple[bool, list[str]]:
    lines = []
    ok = True
    for result in results:
        status = classify(result)
        result["status"] = status
        ok &= status != "FAIL"
        family = f" [{result['family']}]" if result.get("family") else ""
        tail = (
            json.dumps(result.get("detail"))
            if result.get("ok")
            else result.get("error", "")
        )
        if status in ("XFAIL", "XPASS"):
            tail += f" (known gap: {KNOWN_GAPS[result['probe']].note})"
        lines.append(f"{status} {result['probe']}{family}: {tail}")
    if coverage is not None:
        for family in coverage["uncovered"]:
            ok = False
            lines.append(
                f"FAIL kpack family {family}: no probe launched a kernel from it"
            )
        for family in coverage["unknown_families"]:
            ok = False
            lines.append(
                f"FAIL kpack family {family}: staged archive has no probe in this tool"
            )
        for family in coverage["missing_archives"]:
            ok = False
            lines.append(
                f"FAIL kpack family {family}: no {family}_<arch>.kpack archive in the ROCm tree"
            )
    return ok, lines


def cmd_probe(args: argparse.Namespace) -> int:
    probes = args.probe or list(DEFAULT_PROBES)
    unknown = sorted(set(probes) - set(PROBE_FUNCTIONS))
    if unknown:
        print(f"unknown probes: {', '.join(unknown)}", file=sys.stderr)
        return 2
    workdir = (
        Path(args.workdir)
        if args.workdir
        else Path(tempfile.mkdtemp(prefix="therock-kpack-smoke-"))
    )
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    if args.sandbox_root:
        root = Path(args.sandbox_root).resolve()
        (workdir / "tmp").mkdir(exist_ok=True)
        inner = [
            "python3" if args.sandbox_python else sys.executable,
            str(Path(__file__).resolve()),
            "probe",
            "--rocm",
            "/opt/rocm",
            "--arch",
            args.arch,
            "--workdir",
            str(workdir),
        ]
        for name in probes:
            inner += ["--probe", name]
        for path in args.extra_lib_dir:
            inner += ["--extra-lib-dir", str(Path(path).resolve())]
        inner_report = workdir / "report.json"
        inner += ["--json", str(inner_report)]
        binds = [Path(path).resolve() for path in args.extra_lib_dir]
        returncode = subprocess.run(
            bwrap_command(
                root,
                workdir,
                inner,
                sandbox_python=args.sandbox_python,
                extra_binds=binds,
            ),
            check=False,
        ).returncode
        if args.json and inner_report.exists():
            report = json.loads(inner_report.read_text())
            report["sandbox_root"] = str(root)
            report["sandbox_python"] = args.sandbox_python
            Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
        return returncode

    rocm = Path(args.rocm)
    extra = [Path(path) for path in args.extra_lib_dir]
    results = [
        run_probe_child(name, rocm, args.arch, workdir, extra) for name in probes
    ]
    archives = sorted(path.name for path in (rocm / ".kpack").glob("*.kpack"))
    full_run = not args.probe or set(DEFAULT_PROBES) <= set(probes)
    coverage = kpack_coverage(archives, results, args.arch)
    ok, lines = summarize(results, coverage if full_run else None)
    print("\n".join(lines))
    report = {
        "rocm": str(rocm),
        "arch": args.arch,
        "results": results,
        "kpack": coverage,
        "ok": ok,
    }
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
    return 0 if ok else 1


def cmd_run_probe(args: argparse.Namespace) -> int:
    result = run_probe_in_process(
        args.name, Path(args.rocm), args.arch, Path(args.workdir)
    )
    print(json.dumps(result))
    return 0 if result["ok"] else 1


# --------------------------------------------------------------------------
# Package archive checks
# --------------------------------------------------------------------------


@dataclass
class PackageArchive:
    name: str
    depends: list[str]
    files: list[str]


DEPEND_NAME = re.compile(r"^([^<>=]+)")


def read_package_archive(path: Path) -> PackageArchive:
    pkginfo = subprocess.run(
        ["bsdtar", "-xOf", str(path), ".PKGINFO"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    name = ""
    depends = []
    for line in pkginfo.splitlines():
        key, _, value = line.partition(" = ")
        if key == "pkgname":
            name = value
        elif key == "depend":
            depends.append(DEPEND_NAME.match(value).group(1))
    listing = subprocess.run(
        ["bsdtar", "-tf", str(path)], check=True, capture_output=True, text=True
    ).stdout
    files = [
        line
        for line in listing.splitlines()
        if line and not line.endswith("/") and not line.startswith(".")
    ]
    return PackageArchive(name=name, depends=depends, files=files)


def duplicate_owners(packages: list[PackageArchive]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for package in packages:
        for path in package.files:
            owners.setdefault(path, []).append(package.name)
    return {path: names for path, names in sorted(owners.items()) if len(names) > 1}


def root_paths(root: Path) -> set[str]:
    paths = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames + [
            d for d in dirnames if os.path.islink(os.path.join(dirpath, d))
        ]:
            paths.add(os.path.relpath(os.path.join(dirpath, name), root))
    return paths


def compare_root(packages: list[PackageArchive], root: Path) -> dict[str, list[str]]:
    listed = {path for package in packages for path in package.files}
    present = root_paths(root)
    return {"unlisted": sorted(present - listed), "missing": sorted(listed - present)}


def kpack_failures(packages: list[PackageArchive], root: Path, arch: str) -> list[str]:
    sys.path.insert(0, str(REPO_ROOT))
    from generators import therock_split

    owners = {path: package.name for package in packages for path in package.files}
    policy = {
        "repo": {},
        "payload": {"gfx_arch": arch},
        "packages": {
            package.name: {"depends": package.depends} for package in packages
        },
    }
    failures: list = []
    therock_split.check_kpack_refs(root, policy, owners, failures)
    return [f"{failure.subject}: {failure.detail}" for failure in failures]


def cmd_check_packages(args: argparse.Namespace) -> int:
    archives = sorted(
        path
        for path in Path(args.repo).glob("*.pkg.tar.*")
        if not path.name.endswith(".sig")
    )
    packages = [read_package_archive(path) for path in archives]
    problems = [
        f"{path} is owned by {', '.join(names)}"
        for path, names in duplicate_owners(packages).items()
    ]
    report: dict = {
        "packages": len(packages),
        "files": sum(len(package.files) for package in packages),
    }
    if args.root:
        root = Path(args.root)
        diff = compare_root(packages, root)
        problems += [
            f"{path} is on the root but in no package" for path in diff["unlisted"]
        ]
        problems += [
            f"{path} is listed but missing from the root" for path in diff["missing"]
        ]
        kpack = kpack_failures(packages, root, args.arch)
        problems += kpack
        report["kpack_ref_failures"] = len(kpack)
    report["problems"] = problems
    print(f"{report['packages']} packages, {report['files']} files")
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        print(
            "PASS no duplicate owners"
            + (", root matches the file lists, kpack refs owned" if args.root else "")
        )
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
    return 1 if problems else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="launch one kernel per kpack archive family")
    probe.add_argument(
        "--rocm",
        default=str(DEFAULT_ROCM),
        help="ROCm tree to test (default /opt/rocm)",
    )
    probe.add_argument("--arch", default=DEFAULT_ARCH)
    probe.add_argument(
        "--probe",
        action="append",
        choices=ALL_PROBES,
        help=f"probe to run (repeatable; default: {', '.join(DEFAULT_PROBES)})",
    )
    probe.add_argument("--workdir", help="scratch directory (default: a new temp dir)")
    probe.add_argument(
        "--extra-lib-dir",
        action="append",
        default=[],
        help="prepend to LD_LIBRARY_PATH (repeatable)",
    )
    probe.add_argument(
        "--sandbox-root",
        help="run rootless in bubblewrap with <root>/opt/rocm over /opt/rocm",
    )
    probe.add_argument(
        "--sandbox-python",
        action="store_true",
        help="with --sandbox-root, also use the staged CPython from <root>/usr",
    )
    probe.add_argument("--json", help="write the full report here")
    probe.set_defaults(func=cmd_probe)

    run = sub.add_parser(
        "run-probe", help="run one probe in this process (used by probe)"
    )
    run.add_argument("name", choices=ALL_PROBES)
    run.add_argument("--rocm", required=True)
    run.add_argument("--arch", default=DEFAULT_ARCH)
    run.add_argument("--workdir", required=True)
    run.set_defaults(func=cmd_run_probe)

    pkgs = sub.add_parser(
        "check-packages",
        help="check built package archives for ownership and kpack reachability",
    )
    pkgs.add_argument(
        "--repo", required=True, help="directory holding the built *.pkg.tar.* archives"
    )
    pkgs.add_argument(
        "--root",
        help="root the archives were extracted into; enables the root and kpack checks",
    )
    pkgs.add_argument("--arch", default=DEFAULT_ARCH)
    pkgs.add_argument("--json", help="write the report here")
    pkgs.set_defaults(func=cmd_check_packages)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
