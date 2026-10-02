from pathlib import Path
import subprocess


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


def test_stage_migraphx_validates_protobuf_35_1_before_import():
    script = SCRIPT.read_text()
    assert "typeset protobuf_soname=libprotobuf.so.35.1.0" in script
    assert "typeset utf8_validity_soname=libutf8_validity.so.35.1.0" in script

    assert 'local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}' in script
    assert 'local protobuf_prefix=${protobuf_lib_dir:h}' in script
    assert '"-DCMAKE_PREFIX_PATH=$protobuf_prefix;$stage/opt/rocm;/opt/rocm"' in script
    assert "LD_LIBRARY_PATH=$protobuf_lib_dir:${LD_LIBRARY_PATH-}" in script
    assert "protobuf SONAME must be $protobuf_soname" in script
    assert "utf8 validity SONAME must be $utf8_validity_soname" in script
    assert "libprotobuf.so.35.0*" in script
    assert "libutf8_validity.so.35.0*" in script
    assert "libprotobuf.so.34*" in script
    assert "libutf8_validity.so.34*" in script
    assert "libmigraphx_onnx.so" in script
    assert "libmigraphx_tf.so" in script
    assert "staged MIGraphX parser library is not linked against $protobuf_soname" in script
    assert "staged MIGraphX parser library is not linked against $utf8_validity_soname" in script


def test_stage_migraphx_preview_is_dry_run():
    script = SCRIPT.read_text()

    assert "tools/amerge run therock-gfx1151 --dry-run --preview=tree --color=never" in script
