import os
from pathlib import Path
import subprocess

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
    "libmigraphx.so.2",
    "libprotobuf.so.36.1.0",
    "libutf8_validity.so.36.1.0",
    "libabsl_log_internal_check_op.so.2608.0.0",
    "libabsl_strings.so.2608.0.0",
    "libstdc++.so.6",
]

ONNX_PARSER = "lib/migraphx/lib/libmigraphx_onnx.so"
DRIVER = "bin/migraphx-driver"
PYTHON_MODULE = "lib/migraphx.cpython-314-x86_64-linux-gnu.so"
C_API = "lib/libmigraphx_c.so.3.0"

# Paths under the staged opt/rocm, each mapped to its DT_NEEDED sonames. Only
# the parsers link protobuf and Abseil, as in the installed 7.13.0-4 payload.
GOOD_PAYLOAD = {
    ONNX_PARSER: GOOD_PARSER_NEEDED,
    "lib/migraphx/lib/libmigraphx_tf.so": GOOD_PARSER_NEEDED,
    "lib/migraphx/lib/libmigraphx.so.2.0": ["libstdc++.so.6"],
    C_API: ["libmigraphx_onnx.so.2", "libmigraphx_tf.so.2", "libmigraphx.so.2"],
    PYTHON_MODULE: ["libmigraphx_onnx.so.2", "libmigraphx_tf.so.2", "libmigraphx.so.2"],
    DRIVER: ["libmigraphx_onnx.so.2", "libmigraphx_tf.so.2", "libmigraphx.so.2"],
}


def _run_skip_build_with_fake_payload(tmp_path: Path, payload: dict[str, list[str]]):
    """Drive validate_stage with stubbed build tools and a fake readelf."""
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name in ("rsync", "cmake", "ninja"):
        stub = stubs / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    # Each fake ELF holds its DT_NEEDED sonames, one per line.
    readelf = stubs / "readelf"
    readelf.write_text(
        "#!/bin/sh\n"
        "for file; do :; done\n"
        "while IFS= read -r lib; do\n"
        "  [ -n \"$lib\" ] && printf ' 0x0000000000000001 (NEEDED) Shared library: [%s]\\n' \"$lib\"\n"
        "done < \"$file\"\n"
        "exit 0\n"
    )
    readelf.chmod(0o755)
    python = stubs / "python"
    python.write_text("#!/bin/sh\necho 'stub python refuses the import' >&2\nexit 1\n")
    python.chmod(0o755)

    stage = tmp_path / "stage"
    for relative_path, needed in payload.items():
        elf = stage / "opt/rocm" / relative_path
        elf.parent.mkdir(parents=True, exist_ok=True)
        elf.write_text("".join(f"{lib}\n" for lib in needed))
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


def test_stage_migraphx_payload_gate_accepts_protobuf_36_1_and_abseil_2608(tmp_path):
    result = _run_skip_build_with_fake_payload(tmp_path, GOOD_PAYLOAD)

    # The gate passes, so the run reaches the stubbed Python import and stops there.
    assert result.returncode == 2
    assert "checking staged Python import" in result.stdout
    assert "staged MIGraphX" not in result.stderr
    assert "stub python refuses the import" in result.stderr


UNPINNED_MESSAGE = (
    "staged MIGraphX payload links protobuf, utf8_validity, or Abseil other than "
    "libprotobuf.so.36.1.0, libutf8_validity.so.36.1.0, and libabsl_*.so.2608.0.0"
)


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
