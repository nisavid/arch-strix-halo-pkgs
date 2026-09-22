import hashlib
import os
from pathlib import Path
import re
import subprocess


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


def test_stage_migraphx_derives_parser_sonames_at_build_time():
    script = SCRIPT.read_text()

    assert "protobuf_soname=$(read_soname $protobuf_lib_dir/libprotobuf.so)" in script
    assert "utf8_validity_soname=$(read_soname $protobuf_lib_dir/libutf8_validity.so)" in script
    assert "absl_soname=$(read_soname $protobuf_lib_dir/libabsl_base.so)" in script
    assert not re.search(r"libprotobuf\.so\.3\d", script)
    assert not re.search(r"libutf8_validity\.so\.3\d", script)


def test_stage_migraphx_validates_both_parsers_before_import():
    script = SCRIPT.read_text()

    assert "$stage/opt/rocm/lib/migraphx/lib/libmigraphx_onnx.so" in script
    assert "$stage/opt/rocm/lib/migraphx/lib/libmigraphx_tf.so" in script
    assert "libprotobuf.so.*) [[ $dep == $protobuf_soname ]] || stale+=($dep)" in script
    assert "libutf8_validity.so.*) [[ $dep == $utf8_validity_soname ]] || stale+=($dep)" in script
    assert "links a protobuf ABI other than the build target" in script
    assert "staged MIGraphX parser library is not linked against $protobuf_soname" in script
    assert "staged MIGraphX parser library is not linked against $utf8_validity_soname" in script
    assert script.index("links a protobuf ABI other than the build target") < script.index(
        'status "checking staged Python import"'
    )


def test_stage_migraphx_builds_install_target_only():
    script = SCRIPT.read_text()

    assert "cmake --build $src/build --target install -j$jobs" in script
    assert "cmake --build $src/build -j$jobs" not in script


def test_stage_migraphx_preview_is_dry_run():
    script = SCRIPT.read_text()

    assert "tools/amerge run therock-gfx1151 --dry-run --preview=tree --color=never" in script
