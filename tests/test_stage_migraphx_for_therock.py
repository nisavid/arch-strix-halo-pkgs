import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools/stage_migraphx_for_therock.zsh"

MIGRAPHX_2_16_1 = "2487b688c453b9007ac69ff1d79ad6cf9b509901"


def fake_stage(root: Path) -> Path:
    rocm = root / "opt/rocm"
    (rocm / ".info").mkdir(parents=True)
    (rocm / ".info/version").write_text("7.14.1\n")
    compiler = rocm / "lib/llvm/bin/amdclang++"
    compiler.parent.mkdir(parents=True)
    compiler.write_text("#!/bin/sh\nexit 0\n")
    compiler.chmod(0o755)
    return root


def run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def test_stage_migraphx_script_has_valid_zsh_syntax():
    subprocess.run(["zsh", "-n", str(SCRIPT)], check=True)


def test_stage_migraphx_script_help_keeps_deploy_out_of_typical_path():
    result = run_script("--help")

    assert result.returncode == 0
    assert "tools/stage_migraphx_for_therock.zsh --stage <stage> --clean\n" in result.stdout
    assert "--clean --deploy" not in result.stdout
    assert "--deploy" in result.stdout
    assert "--skip-build" in result.stdout
    assert "--stage PATH" in result.stdout
    assert "--migraphx-ref REF" in result.stdout
    assert "--protobuf-prefix PATH" in result.stdout
    assert "--protobuf-dir PATH" in result.stdout
    assert "--with-ck" in result.stdout
    assert "--with-mlir" in result.stdout
    assert "tools/stage_therock_payload.py" in result.stdout


def test_stage_migraphx_requires_a_staged_therock_payload(tmp_path):
    env = {"THEROCK_STAGE_ROOT": ""}
    result = run_script("--skip-build", env=env)
    assert result.returncode == 2
    assert "pass --stage or set THEROCK_STAGE_ROOT" in result.stderr

    result = run_script("--stage", str(tmp_path / "empty"), "--skip-build")
    assert result.returncode == 2
    assert "no staged TheRock payload" in result.stderr
    assert "tools/stage_therock_payload.py" in result.stderr


def test_stage_migraphx_clean_keeps_stage_and_preserves_path_for_commands(tmp_path):
    stage = fake_stage(tmp_path / "stage")
    src = tmp_path / "src"
    prefix = tmp_path / "protobuf-prefix"
    src.mkdir()
    prefix.mkdir()

    result = run_script(
        "--stage",
        str(stage),
        "--src",
        str(src),
        "--protobuf-prefix",
        str(prefix),
        "--clean",
        "--skip-build",
    )

    assert result.returncode == 2
    assert "command not found" not in result.stderr
    assert "--skip-build needs an existing build dir" in result.stderr
    assert not src.exists()
    assert not prefix.exists()
    assert (stage / "opt/rocm/.info/version").is_file()


def test_stage_migraphx_rejects_protobuf_packages_that_miss_the_pin(tmp_path):
    stage = fake_stage(tmp_path / "stage")
    src = tmp_path / "src"
    (src / "build").mkdir(parents=True)
    pkg_dir = tmp_path / "pkgs"
    pkg_dir.mkdir()
    bogus = pkg_dir / "protobuf-36.1-1-x86_64.pkg.tar.zst"
    bogus.write_bytes(b"not the pinned package")

    result = run_script(
        "--stage",
        str(stage),
        "--src",
        str(src),
        "--protobuf-prefix",
        str(tmp_path / "prefix"),
        "--protobuf-pkg-dir",
        str(pkg_dir),
        "--skip-build",
    )

    assert result.returncode == 2
    assert f"sha256 mismatch for {bogus}" in result.stderr
    assert hashlib.sha256(bogus.read_bytes()).hexdigest() in result.stderr
    assert not (tmp_path / "prefix").exists()


def test_stage_migraphx_pins_2_16_1_and_fetches_by_sha():
    script = SCRIPT.read_text()

    assert f"typeset migraphx_ref={MIGRAPHX_2_16_1}" in script
    assert "run git init $src" in script
    assert "git -C $src fetch --depth 1 origin $migraphx_ref" in script
    assert "git -C $src checkout --detach FETCH_HEAD" in script
    assert "--branch develop" not in script


def test_stage_migraphx_builds_against_the_stage_without_host_rocm():
    script = SCRIPT.read_text()

    assert '"-DCMAKE_PREFIX_PATH=$protobuf_prefix_root;$rocm"' in script
    assert "-DCMAKE_C_COMPILER=$rocm/lib/llvm/bin/amdclang" in script
    assert "-DCMAKE_CXX_COMPILER=$rocm/lib/llvm/bin/amdclang++" in script
    assert "ROCM_PATH=$rocm" in script
    assert "/opt/rocm/lib/llvm/bin" not in script
    assert ";/opt/rocm\"" not in script
    assert "rsync" not in script
    assert "copy_current_rocm_into_stage" not in script


def test_stage_migraphx_takes_pybind11_from_the_python_module():
    script = SCRIPT.read_text()

    assert "pybind11_dir=$(python -m pybind11 --cmakedir)" in script
    assert "-Dpybind11_DIR=$pybind11_dir" in script


def test_stage_migraphx_configures_current_staged_root_feature_gates():
    script = SCRIPT.read_text()

    assert "-DMIGRAPHX_USE_COMPOSABLEKERNEL=$ck" in script
    assert "-DMIGRAPHX_ENABLE_MLIR=$mlir" in script
    assert "-DROCM_ENABLE_CLANG_TIDY=OFF" in script
    assert "typeset with_mlir=0" in script


def test_stage_migraphx_keeps_no_mlir_stubs_without_rockenums_replacement():
    script = SCRIPT.read_text()

    assert "patch_migraphx_source_for_staged_root" in script
    assert "void dump_mlir_to_file(" in script
    assert "bool is_module_fusible(" in script
    assert "void adjust_param_shapes(" in script
    assert "void dump_mlir_to_mxr(" in script
    # AMDMIGraphX 2.16 guards the include upstream (#4962); a replacement for
    # it would no longer find its anchor and would fail the build.
    assert "#include <mlir-c/Dialect/RockEnums.h>" not in script


def test_stage_migraphx_uses_isolated_pinned_protobuf_prefix():
    script = SCRIPT.read_text()

    assert "protobuf-36.1-1-x86_64.pkg.tar.zst 3d63417c8fbe2354bea29b23c338baf3f03c9438e0127c5519d6dddc4825185c" in script
    assert (
        "abseil-cpp-20260817.0-2-x86_64.pkg.tar.zst 4ecd2e4e2cf7096edfad8522df68d0d9adbe41ce7a6689c1915905342ae6a016"
        in script
    )
    assert "https://archive.archlinux.org/packages" in script
    assert "protobuf_dir=$protobuf_prefix/usr/lib/cmake/protobuf" in script
    assert "-Dprotobuf_DIR=$protobuf_dir" in script
    assert "LD_LIBRARY_PATH=$protobuf_lib_dir:${LD_LIBRARY_PATH-}" in script
    assert "LD_LIBRARY_PATH=$protobuf_lib_dir:$stage/opt/rocm/lib:${LD_LIBRARY_PATH-}" in script


def test_stage_migraphx_pins_protobuf_36_1_and_abseil_2608_in_the_prefix_check():
    script = SCRIPT.read_text()

    assert "typeset protobuf_soname=libprotobuf.so.36.1.0" in script
    assert "typeset utf8_validity_soname=libutf8_validity.so.36.1.0" in script
    assert "typeset abseil_soversion=2608.0.0" in script
    assert "local absl_dir=$protobuf_lib_dir/cmake/absl" in script
    assert "-Dabsl_DIR=$absl_dir" in script
    assert "protobuf SONAME must be $protobuf_soname" in script
    assert "utf8 validity SONAME must be $utf8_validity_soname" in script
    assert "Abseil CMake config directory is missing: $absl_dir" in script
    assert "Abseil SONAME must be libabsl_base.so.$abseil_soversion" in script
    # The prefix check runs before any build or install step.
    assert script.index("prepare_protobuf_prefix\ncheck_protobuf_prefix\n") < script.index(
        "  install_existing_build\n"
    )


def test_stage_migraphx_validates_both_parsers_before_import():
    script = SCRIPT.read_text()

    assert "$stage/opt/rocm/lib/migraphx/lib/libmigraphx_onnx.so" in script
    assert "$stage/opt/rocm/lib/migraphx/lib/libmigraphx_tf.so" in script
    assert "staged MIGraphX parser library is not linked against $protobuf_soname" in script
    assert "staged MIGraphX parser library is not linked against $utf8_validity_soname" in script
    assert script.index("staged MIGraphX parser library links no Abseil libraries") < script.index(
        'status "checking staged Python import"'
    )


def test_stage_migraphx_builds_install_target_only():
    script = SCRIPT.read_text()

    assert "cmake --build $src/build --target install -j$jobs" in script
    assert "cmake --build $src/build -j$jobs" not in script


def test_stage_migraphx_preview_is_dry_run():
    script = SCRIPT.read_text()

    assert "tools/amerge run therock-gfx1151 --dry-run --preview=tree --color=never" in script


def test_stage_migraphx_shims_rocm_add_version_resource_only_when_the_stage_lacks_it():
    script = SCRIPT.read_text()

    # TheRock 7.14.1 ships rocm-cmake 0.14.0, which predates the upstream
    # function; upstream only acts on WIN32, so the shim is a Linux no-op.
    assert "grep -q 'function(rocm_add_version_resource' $rocm_cmake_dir/*.cmake && return" in script
    assert "function(rocm_add_version_resource TARGET NAME DESCRIPTION)\nendfunction()" in script
    assert "configure_args+=(-DCMAKE_PROJECT_INCLUDE=$rocm_cmake_compat)" in script
    assert script.index("write_rocm_cmake_compat\n  build_and_install_migraphx") > 0


GOOD_PARSER_NEEDED = [
    "libmigraphx.so.2016001",
    "libprotobuf.so.36.1.0",
    "libutf8_validity.so.36.1.0",
    "libabsl_log_internal_check_op.so.2608.0.0",
    "libabsl_strings.so.2608.0.0",
    "libstdc++.so.6",
]
MIGRAPHX_USER_NEEDED = [
    "libmigraphx_onnx.so.2016001",
    "libmigraphx_tf.so.2016001",
    "libmigraphx.so.2016001",
    "libstdc++.so.6",
]

ONNX_PARSER = "lib/migraphx/lib/libmigraphx_onnx.so.2016001.0"
TF_PARSER = "lib/migraphx/lib/libmigraphx_tf.so.2016001.0"
DRIVER = "bin/migraphx-driver"
HIPRTC_DRIVER = "bin/migraphx-hiprtc-driver"
FLATC = "bin/flatc"
PYTHON_MODULE = "lib/migraphx.cpython-314-x86_64-linux-gnu.so"
C_API = "lib/libmigraphx_c.so.3.0"

# The 13 regular ELF files of migraphx-gfx1151 7.14.1-1 (AMDMIGraphX 2.16.1),
# as paths under the staged opt/rocm, each mapped to a representative subset of
# its DT_NEEDED sonames. Only the parsers link protobuf and Abseil.
GOOD_PAYLOAD = {
    FLATC: ["libstdc++.so.6", "libc.so.6"],
    DRIVER: MIGRAPHX_USER_NEEDED,
    HIPRTC_DRIVER: ["libmigraphx_gpu.so.2016001", "libhiprtc.so.7", "libmigraphx.so.2016001"],
    C_API: MIGRAPHX_USER_NEEDED,
    "lib/libmigraphx_py.so": ["libmigraphx.so.2016001", "libstdc++.so.6"],
    "lib/libmigraphx_py_3.14.so": ["libpython3.14.so.1.0", "libmigraphx.so.2016001"],
    PYTHON_MODULE: MIGRAPHX_USER_NEEDED,
    "lib/migraphx/lib/libmigraphx.so.2016001.0": ["libstdc++.so.6"],
    "lib/migraphx/lib/libmigraphx_device.so.2016001.0": ["libmigraphx.so.2016001", "libamdhip64.so.7"],
    "lib/migraphx/lib/libmigraphx_gpu.so.2016001.0": ["libmigraphx.so.2016001"],
    ONNX_PARSER: GOOD_PARSER_NEEDED,
    "lib/migraphx/lib/libmigraphx_ref.so.2016001.0": ["libmigraphx.so.2016001"],
    TF_PARSER: GOOD_PARSER_NEEDED,
}

# The package's versioned symlink chains as (link, target), each link after
# the link it targets.
SYMLINKS = [
    ("lib/libmigraphx_c.so.3", "libmigraphx_c.so.3.0"),
    ("lib/libmigraphx_c.so", "libmigraphx_c.so.3"),
    *(
        (f"lib/migraphx/lib/libmigraphx{part}.so.2016001", f"libmigraphx{part}.so.2016001.0")
        for part in ("", "_device", "_gpu", "_onnx", "_ref", "_tf")
    ),
    *(
        (f"lib/migraphx/lib/libmigraphx{part}.so", f"libmigraphx{part}.so.2016001")
        for part in ("", "_device", "_gpu", "_onnx", "_ref", "_tf")
    ),
]

ELF_MAGIC = "\x7fELF"
GOOD_PREFIX_SONAMES = {
    "libprotobuf.so": "libprotobuf.so.36.1.0",
    "libutf8_validity.so": "libutf8_validity.so.36.1.0",
    "libabsl_base.so": "libabsl_base.so.2608.0.0",
}


def test_stage_migraphx_fake_payload_matches_the_packaged_filelist():
    filelist = set(
        (REPO_ROOT / "packages/therock-gfx1151/filelists/migraphx-gfx1151.txt")
        .read_text()
        .splitlines()
    )
    fixture_paths = {*GOOD_PAYLOAD, *(link for link, _target in SYMLINKS)}
    assert {f"opt/rocm/{path}" for path in fixture_paths} <= filelist

    script = SCRIPT.read_text()
    assert f"typeset migraphx_min_elfs={len(GOOD_PAYLOAD)}\n" in script


def _run_skip_build_with_fake_payload(
    tmp_path: Path,
    payload: dict[str, list[str]],
    non_elf_files: dict[str, str] | None = None,
    prefix_sonames: dict[str, str] | None = None,
    absl_cmake: bool = True,
):
    """Drive the prefix check and validate_stage with stubbed build tools.

    A fake readelf reports a SONAME for files whose first line is SONAME and
    otherwise treats each payload file as the ELF magic followed by its
    DT_NEEDED sonames, one per line; it fails on a file with an UNREADABLE
    line. Each non-ELF file holds only its given text.
    """
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name in ("cmake", "ninja"):
        stub = stubs / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    readelf = stubs / "readelf"
    readelf.write_text(
        "#!/bin/sh\n"
        "for file; do :; done\n"
        "if grep -qx UNREADABLE \"$file\"; then\n"
        "  echo 'readelf: Error: not an ELF file' >&2; exit 1\n"
        "fi\n"
        "if [ \"$(head -n 1 \"$file\")\" = SONAME ]; then\n"
        "  printf ' 0x000000000000000e (SONAME) Library soname: [%s]\\n' \"$(sed -n 2p \"$file\")\"; exit 0\n"
        "fi\n"
        "tail -n +2 \"$file\" | while IFS= read -r lib; do\n"
        "  [ -n \"$lib\" ] && printf ' 0x0000000000000001 (NEEDED) Shared library: [%s]\\n' \"$lib\"\n"
        "done\n"
        "exit 0\n"
    )
    readelf.chmod(0o755)
    # The ELF listing runs on the real interpreter; only the import is refused.
    python = stubs / "python"
    python.write_text(
        "#!/bin/sh\n"
        "script=$(cat)\n"
        "case $script in\n"
        "  *'import migraphx'*) echo 'stub python refuses the import' >&2; exit 1 ;;\n"
        "esac\n"
        f"printf '%s\\n' \"$script\" | exec {shlex.quote(sys.executable)} \"$@\"\n"
    )
    python.chmod(0o755)

    stage = fake_stage(tmp_path / "stage")
    rocm = stage / "opt/rocm"
    for relative_path, needed in payload.items():
        elf = rocm / relative_path
        elf.parent.mkdir(parents=True, exist_ok=True)
        elf.write_text("".join(f"{line}\n" for line in [ELF_MAGIC, *needed]))
    for relative_path, text in (non_elf_files or {}).items():
        path = rocm / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    for relative_path, target in SYMLINKS:
        link = rocm / relative_path
        if (link.parent / target).exists():
            link.symlink_to(target)
    src = tmp_path / "src"
    (src / "build").mkdir(parents=True)

    # A protobuf prefix whose libraries report the given sonames.
    lib_dir = tmp_path / "prefix/usr/lib"
    protobuf_dir = lib_dir / "cmake/protobuf"
    protobuf_dir.mkdir(parents=True)
    if absl_cmake:
        (lib_dir / "cmake/absl").mkdir()
    for name, soname in (GOOD_PREFIX_SONAMES if prefix_sonames is None else prefix_sonames).items():
        (lib_dir / name).write_text(f"SONAME\n{soname}\n")

    # An empty ZDOTDIR keeps user startup files from putting real tools ahead of the stubs.
    zdotdir = tmp_path / "zdotdir"
    zdotdir.mkdir()
    env = dict(os.environ)
    env["ZDOTDIR"] = str(zdotdir)
    env["PATH"] = f"{stubs}:{env['PATH']}"
    return subprocess.run(
        [
            str(SCRIPT),
            "--stage",
            str(stage),
            "--src",
            str(src),
            "--protobuf-dir",
            str(protobuf_dir),
            "--skip-build",
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def _checked_elfs(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith("opt/rocm/")]


def test_stage_migraphx_payload_gate_accepts_protobuf_36_1_and_abseil_2608(tmp_path):
    result = _run_skip_build_with_fake_payload(tmp_path, GOOD_PAYLOAD)

    # The gate passes, so the run reaches the stubbed Python import and stops there.
    assert result.returncode == 2
    assert "building against libprotobuf.so.36.1.0, libutf8_validity.so.36.1.0" in result.stdout
    assert _checked_elfs(result.stdout) == sorted(f"opt/rocm/{path}" for path in GOOD_PAYLOAD)
    assert "checking the DT_NEEDED entries of 13 staged migraphx-gfx1151 ELF files" in result.stdout
    assert "checking staged Python import" in result.stdout
    assert "staged MIGraphX" not in result.stderr
    assert "stub python refuses the import" in result.stderr


@pytest.mark.parametrize(
    ("prefix_sonames", "absl_cmake", "message"),
    [
        (
            {**GOOD_PREFIX_SONAMES, "libprotobuf.so": "libprotobuf.so.35.1.0"},
            True,
            "protobuf SONAME must be libprotobuf.so.36.1.0",
        ),
        (
            {**GOOD_PREFIX_SONAMES, "libutf8_validity.so": "libutf8_validity.so.37.0.0"},
            True,
            "utf8 validity SONAME must be libutf8_validity.so.36.1.0",
        ),
        (
            {**GOOD_PREFIX_SONAMES, "libabsl_base.so": "libabsl_base.so.2605.0.0"},
            True,
            "Abseil SONAME must be libabsl_base.so.2608.0.0",
        ),
        (
            {k: v for k, v in GOOD_PREFIX_SONAMES.items() if k != "libabsl_base.so"},
            True,
            "Abseil library is missing",
        ),
        (GOOD_PREFIX_SONAMES, False, "Abseil CMake config directory is missing"),
    ],
    ids=["protobuf", "utf8-validity", "abseil-soname", "abseil-missing", "abseil-cmake-missing"],
)
def test_stage_migraphx_rejects_a_protobuf_prefix_off_the_pins_before_install(
    tmp_path, prefix_sonames, absl_cmake, message
):
    result = _run_skip_build_with_fake_payload(
        tmp_path, GOOD_PAYLOAD, prefix_sonames=prefix_sonames, absl_cmake=absl_cmake
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert "installing existing AMDMIGraphX build" not in result.stdout
    assert "checking staged MIGraphX payload" not in result.stdout


def test_stage_migraphx_payload_gate_checks_every_regular_elf_the_package_owns(tmp_path):
    # Names no pattern would expect: one owned through the opt/rocm/lib/migraphx
    # path override, one through the migraphx binary prefix.
    unlisted = {
        "lib/migraphx/lib/plugin-without-so-suffix": ["libstdc++.so.6"],
        "bin/migraphx-unlisted-tool": ["libstdc++.so.6"],
    }
    # Stale links that the gate must not read: text without the ELF magic in a
    # MIGraphX-owned path, and an ELF that another split package owns.
    non_elf_files = {"lib/migraphx/lib/README": "libprotobuf.so.35.1.0\n"}
    other_package = {"lib/librocblas.so.5.0": ["libprotobuf.so.35.1.0"]}
    payload = {**GOOD_PAYLOAD, **unlisted, **other_package}
    result = _run_skip_build_with_fake_payload(tmp_path, payload, non_elf_files)

    assert result.returncode == 2
    assert _checked_elfs(result.stdout) == sorted(
        f"opt/rocm/{path}" for path in {**GOOD_PAYLOAD, **unlisted}
    )
    assert "checking the DT_NEEDED entries of 15 staged migraphx-gfx1151 ELF files" in result.stdout
    assert "staged MIGraphX" not in result.stderr
    assert "stub python refuses the import" in result.stderr


UNPINNED_MESSAGE = (
    "staged MIGraphX payload links protobuf, utf8_validity, or Abseil other than "
    "libprotobuf.so.36.1.0, libutf8_validity.so.36.1.0, and libabsl_*.so.2608.0.0"
)


@pytest.mark.parametrize(
    "elf", ["lib/migraphx/lib/plugin-without-so-suffix", "bin/migraphx-unlisted-tool"]
)
def test_stage_migraphx_payload_gate_rejects_unpinned_links_in_unlisted_elf_names(tmp_path, elf):
    payload = {**GOOD_PAYLOAD, elf: ["libstdc++.so.6", "libprotobuf.so.35.1.0"]}
    result = _run_skip_build_with_fake_payload(tmp_path, payload)

    assert result.returncode == 2
    assert f"staged opt/rocm/{elf} links: libprotobuf.so.35.1.0\n" in result.stderr
    assert UNPINNED_MESSAGE in result.stderr
    assert "checking staged Python import" not in result.stdout


WITHOUT_FLATC = {path: needed for path, needed in GOOD_PAYLOAD.items() if path != FLATC}


@pytest.mark.parametrize(
    "non_elf_files",
    [
        {},
        # A flatc without the ELF magic is not an ELF the gate can check.
        {FLATC: "libstdc++.so.6\n"},
    ],
    ids=["missing", "not-elf"],
)
def test_stage_migraphx_payload_gate_rejects_fewer_elfs_than_expected(tmp_path, non_elf_files):
    result = _run_skip_build_with_fake_payload(tmp_path, WITHOUT_FLATC, non_elf_files)

    assert result.returncode == 2
    assert "staged migraphx-gfx1151 payload has 12 regular ELF files; expected at least 13" in (
        result.stderr
    )
    assert "checking the DT_NEEDED entries" not in result.stdout
    assert "checking staged Python import" not in result.stdout


def test_stage_migraphx_payload_gate_rejects_a_stage_without_migraphx_elfs(tmp_path):
    result = _run_skip_build_with_fake_payload(tmp_path, {})

    assert result.returncode == 2
    assert "staged root still has no MIGraphX payload" in result.stderr
    assert "checking staged Python import" not in result.stdout


def test_stage_migraphx_payload_gate_fails_when_readelf_cannot_read_an_elf(tmp_path):
    payload = {**GOOD_PAYLOAD, DRIVER: ["UNREADABLE"]}
    result = _run_skip_build_with_fake_payload(tmp_path, payload)

    assert result.returncode == 2
    assert "readelf cannot read" in result.stderr
    assert "checking staged Python import" not in result.stdout


@pytest.mark.parametrize(
    "unpinned",
    [
        "libprotobuf.so.35.1.0",
        "libutf8_validity.so.35.1.0",
        "libprotobuf.so.37.0.0",
        "libutf8_validity.so.37.0.0",
        "libabsl_strings.so.2605.0.0",
        "libabsl_strings.so.2601.0.0",
    ],
)
def test_stage_migraphx_payload_gate_rejects_unpinned_parser_links(tmp_path, unpinned):
    payload = {**GOOD_PAYLOAD, ONNX_PARSER: [*GOOD_PARSER_NEEDED, unpinned]}
    result = _run_skip_build_with_fake_payload(tmp_path, payload)

    assert result.returncode == 2
    assert f"staged opt/rocm/{ONNX_PARSER} links: {unpinned}\n" in result.stderr
    assert UNPINNED_MESSAGE in result.stderr
    assert "checking staged Python import" not in result.stdout


@pytest.mark.parametrize(
    ("elf", "unpinned"),
    [
        (DRIVER, ["libprotobuf.so.35.1.0", "libabsl_strings.so.2605.0.0"]),
        (PYTHON_MODULE, ["libabsl_base.so.2605.0.0"]),
        (C_API, ["libutf8_validity.so.37.0.0"]),
        (HIPRTC_DRIVER, ["libprotobuf.so.35.1.0"]),
        (HIPRTC_DRIVER, ["libabsl_strings.so.2605.0.0"]),
        (FLATC, ["libprotobuf.so.34.1.0", "libutf8_validity.so.34.1.0"]),
        (FLATC, ["libabsl_hash.so.2605.0.0"]),
    ],
)
def test_stage_migraphx_payload_gate_rejects_unpinned_links_outside_parsers(
    tmp_path, elf, unpinned
):
    payload = {**GOOD_PAYLOAD, elf: [*GOOD_PAYLOAD[elf], *unpinned]}
    result = _run_skip_build_with_fake_payload(tmp_path, payload)

    assert result.returncode == 2
    assert f"staged opt/rocm/{elf} links: {', '.join(unpinned)}\n" in result.stderr
    assert UNPINNED_MESSAGE in result.stderr
    assert "checking staged Python import" not in result.stdout


@pytest.mark.parametrize("pinned", ["libprotobuf.so.36.1.0", "libutf8_validity.so.36.1.0"])
@pytest.mark.parametrize("parser", [ONNX_PARSER, TF_PARSER])
def test_stage_migraphx_parser_gate_requires_pinned_protobuf_links(tmp_path, parser, pinned):
    needed = [lib for lib in GOOD_PARSER_NEEDED if lib != pinned]
    result = _run_skip_build_with_fake_payload(tmp_path, {**GOOD_PAYLOAD, parser: needed})

    assert result.returncode == 2
    assert f"staged MIGraphX parser library is not linked against {pinned}" in result.stderr
    assert "checking staged Python import" not in result.stdout


@pytest.mark.parametrize("parser", [ONNX_PARSER, TF_PARSER])
def test_stage_migraphx_parser_gate_requires_abseil_links(tmp_path, parser):
    needed = [lib for lib in GOOD_PARSER_NEEDED if not lib.startswith("libabsl_")]
    result = _run_skip_build_with_fake_payload(tmp_path, {**GOOD_PAYLOAD, parser: needed})

    assert result.returncode == 2
    assert "staged MIGraphX parser library links no Abseil libraries" in result.stderr
    assert "checking staged Python import" not in result.stdout
