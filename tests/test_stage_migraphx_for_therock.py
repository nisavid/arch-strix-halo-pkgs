import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools/stage_migraphx_for_therock.zsh"


def test_stage_migraphx_script_has_valid_zsh_syntax():
    subprocess.run(["zsh", "-n", str(SCRIPT)], check=True)


def test_stage_migraphx_script_help_keeps_deploy_out_of_typical_path():
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "tools/stage_migraphx_for_therock.zsh --clean\n" in result.stdout
    assert "tools/stage_migraphx_for_therock.zsh --clean --deploy" not in result.stdout
    assert "--deploy" in result.stdout
    assert "--skip-build" in result.stdout
    assert "--stage PATH" in result.stdout
    assert "--protobuf-dir PATH" in result.stdout
    assert "--rocm-root PATH" in result.stdout
    assert "--migraphx-ref REF" in result.stdout
    assert "--with-ck" in result.stdout
    assert "--with-mlir" in result.stdout


def test_stage_migraphx_clean_preserves_path_for_commands(tmp_path):
    stage = tmp_path / "stage"
    src = tmp_path / "src"
    stage.mkdir()
    src.mkdir()

    result = subprocess.run(
        [
            str(SCRIPT),
            "--stage",
            str(stage),
            "--src",
            str(src),
            "--clean",
            "--skip-build",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "command not found" not in result.stderr
    assert "--skip-build needs an existing build dir" in result.stderr


def test_stage_migraphx_configures_current_staged_root_feature_gates():
    script = SCRIPT.read_text()
    assert "typeset migraphx_ref=b69836e6c97de179a80d764d24574edba7ba1b1b" in script
    assert "git -C $src fetch --depth 1 origin $migraphx_ref" in script
    assert "python -m pybind11 --cmakedir" in script
    assert "-Dpybind11_DIR=$pybind11_dir" in script

    assert "-DMIGRAPHX_USE_COMPOSABLEKERNEL=$ck" in script
    assert "-DMIGRAPHX_ENABLE_MLIR=$mlir" in script
    assert "-DROCM_ENABLE_CLANG_TIDY=OFF" in script


def test_stage_migraphx_guards_unguarded_rocmlir_header():
    script = SCRIPT.read_text()

    assert "patch_migraphx_source_for_staged_root" in script
    assert "mlir-c/Dialect/RockEnums.h" in script
    assert "#ifdef MIGRAPHX_MLIR" in script
    assert "bool is_module_fusible" in script
    assert "void dump_mlir_to_mxr" in script


def test_stage_migraphx_stage_copy_does_not_preserve_owner_or_group():
    script = SCRIPT.read_text()

    assert "rsync -aH --no-owner --no-group --delete" in script


def test_stage_migraphx_builds_install_target_only():
    script = SCRIPT.read_text()

    assert "cmake --build $src/build --target install -j$jobs" in script
    assert "cmake --build $src/build -j$jobs" not in script


def test_stage_migraphx_validates_protobuf_36_1_and_abseil_2608_before_import():
    script = SCRIPT.read_text()
    assert "typeset protobuf_soname=libprotobuf.so.36.1.0" in script
    assert "typeset utf8_validity_soname=libutf8_validity.so.36.1.0" in script
    assert "typeset abseil_soversion=2608.0.0" in script

    assert 'local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}' in script
    assert 'local protobuf_prefix=${protobuf_lib_dir:h}' in script
    assert 'local absl_dir=$protobuf_lib_dir/cmake/absl' in script
    assert '"-DCMAKE_PREFIX_PATH=$protobuf_prefix;$stage/opt/rocm;$rocm_root"' in script
    assert "-DCMAKE_CXX_COMPILER=$rocm_root/lib/llvm/bin/amdclang++" in script
    assert "-Dabsl_DIR=$absl_dir" in script
    assert "LD_LIBRARY_PATH=$protobuf_lib_dir:${LD_LIBRARY_PATH-}" in script
    assert "protobuf SONAME must be $protobuf_soname" in script
    assert "utf8 validity SONAME must be $utf8_validity_soname" in script
    assert "Abseil CMake config directory is missing: $absl_dir" in script
    assert "Abseil SONAME must be libabsl_base.so.$abseil_soversion" in script
    assert "libmigraphx_onnx.so" in script
    assert "libmigraphx_tf.so" in script
    assert "staged MIGraphX parser library is not linked against $protobuf_soname" in script
    assert "staged MIGraphX parser library is not linked against $utf8_validity_soname" in script


GOOD_PARSER_NEEDED = [
    "libmigraphx.so.2016000",
    "libprotobuf.so.36.1.0",
    "libutf8_validity.so.36.1.0",
    "libabsl_log_internal_check_op.so.2608.0.0",
    "libabsl_strings.so.2608.0.0",
    "libstdc++.so.6",
]
MIGRAPHX_USER_NEEDED = [
    "libmigraphx_onnx.so.2016000",
    "libmigraphx_tf.so.2016000",
    "libmigraphx.so.2016000",
    "libstdc++.so.6",
]

ONNX_PARSER = "lib/migraphx/lib/libmigraphx_onnx.so.2016000.0"
TF_PARSER = "lib/migraphx/lib/libmigraphx_tf.so.2016000.0"
DRIVER = "bin/migraphx-driver"
HIPRTC_DRIVER = "bin/migraphx-hiprtc-driver"
FLATC = "bin/flatc"
IREE_COMPILER = "lib/libIREECompiler.so"
PYTHON_MODULE = "lib/migraphx.cpython-314-x86_64-linux-gnu.so"
C_API = "lib/libmigraphx_c.so.3.0"

# The 14 regular ELF files of the installed migraphx-gfx1151 7.13.0-4, as paths
# under the staged opt/rocm, each mapped to a representative subset of its
# DT_NEEDED sonames. Only the parsers link protobuf and Abseil.
GOOD_PAYLOAD = {
    FLATC: ["libstdc++.so.6", "libc.so.6"],
    DRIVER: MIGRAPHX_USER_NEEDED,
    HIPRTC_DRIVER: ["libmigraphx_gpu.so.2016000", "libhiprtc.so.7", "libmigraphx.so.2016000"],
    IREE_COMPILER: ["libstdc++.so.6", "libc.so.6"],
    C_API: MIGRAPHX_USER_NEEDED,
    "lib/libmigraphx_py.so": ["libmigraphx.so.2016000", "libstdc++.so.6"],
    "lib/libmigraphx_py_3.14.so": ["libpython3.14.so.1.0", "libmigraphx.so.2016000"],
    PYTHON_MODULE: MIGRAPHX_USER_NEEDED,
    "lib/migraphx/lib/libmigraphx.so.2016000.0": ["libstdc++.so.6"],
    "lib/migraphx/lib/libmigraphx_device.so.2016000.0": ["libmigraphx.so.2016000", "libamdhip64.so.7"],
    "lib/migraphx/lib/libmigraphx_gpu.so.2016000.0": ["libmigraphx.so.2016000"],
    ONNX_PARSER: GOOD_PARSER_NEEDED,
    "lib/migraphx/lib/libmigraphx_ref.so.2016000.0": ["libmigraphx.so.2016000"],
    TF_PARSER: GOOD_PARSER_NEEDED,
}

# The package's versioned symlink chains as (link, target), each link after
# the link it targets.
SYMLINKS = [
    ("lib/libmigraphx_c.so.3", "libmigraphx_c.so.3.0"),
    ("lib/libmigraphx_c.so", "libmigraphx_c.so.3"),
    *(
        (f"lib/migraphx/lib/libmigraphx{part}.so.2016000", f"libmigraphx{part}.so.2016000.0")
        for part in ("", "_device", "_gpu", "_onnx", "_ref", "_tf")
    ),
    *(
        (f"lib/migraphx/lib/libmigraphx{part}.so", f"libmigraphx{part}.so.2016000")
        for part in ("", "_device", "_gpu", "_onnx", "_ref", "_tf")
    ),
]

ELF_MAGIC = "\x7fELF"


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
):
    """Drive validate_stage with stubbed build tools and a fake readelf.

    Each payload file starts with the ELF magic and then lists its DT_NEEDED
    sonames, one per line. Each non-ELF file holds only its given text.
    """
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name in ("rsync", "cmake", "ninja"):
        stub = stubs / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    readelf = stubs / "readelf"
    readelf.write_text(
        "#!/bin/sh\n"
        "for file; do :; done\n"
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

    stage = tmp_path / "stage"
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
    # The rsync stub copies nothing, so an empty ROCm root keeps the run
    # independent of any installed ROCm tree.
    rocm_root = tmp_path / "rocm"
    rocm_root.mkdir()

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
            "--rocm-root",
            str(rocm_root),
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
    assert _checked_elfs(result.stdout) == sorted(f"opt/rocm/{path}" for path in GOOD_PAYLOAD)
    assert "checking the DT_NEEDED entries of 14 staged migraphx-gfx1151 ELF files" in result.stdout
    assert "checking staged Python import" in result.stdout
    assert "staged MIGraphX" not in result.stderr
    assert "stub python refuses the import" in result.stderr


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
    assert "checking the DT_NEEDED entries of 16 staged migraphx-gfx1151 ELF files" in result.stdout
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
    assert "staged migraphx-gfx1151 payload has 13 regular ELF files; expected at least 14" in (
        result.stderr
    )
    assert "checking the DT_NEEDED entries" not in result.stdout
    assert "checking staged Python import" not in result.stdout


def test_stage_migraphx_payload_gate_rejects_a_stage_without_migraphx_elfs(tmp_path):
    result = _run_skip_build_with_fake_payload(tmp_path, {})

    assert result.returncode == 2
    assert "staged root still has no MIGraphX payload" in result.stderr
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
        (IREE_COMPILER, ["libprotobuf.so.35.1.0"]),
        (IREE_COMPILER, ["libabsl_base.so.2601.0.0"]),
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
def test_stage_migraphx_parser_gate_requires_pinned_protobuf_links(tmp_path, pinned):
    needed = [lib for lib in GOOD_PARSER_NEEDED if lib != pinned]
    result = _run_skip_build_with_fake_payload(tmp_path, {**GOOD_PAYLOAD, ONNX_PARSER: needed})

    assert result.returncode == 2
    assert f"staged MIGraphX parser library is not linked against {pinned}" in result.stderr
    assert "checking staged Python import" not in result.stdout


def test_stage_migraphx_parser_gate_requires_abseil_links(tmp_path):
    needed = [lib for lib in GOOD_PARSER_NEEDED if not lib.startswith("libabsl_")]
    result = _run_skip_build_with_fake_payload(tmp_path, {**GOOD_PAYLOAD, ONNX_PARSER: needed})

    assert result.returncode == 2
    assert "staged MIGraphX parser library links no Abseil libraries" in result.stderr
    assert "checking staged Python import" not in result.stdout


def test_stage_migraphx_preview_is_dry_run():
    script = SCRIPT.read_text()

    assert "tools/amerge run therock-gfx1151 --dry-run --preview=tree --color=never" in script
