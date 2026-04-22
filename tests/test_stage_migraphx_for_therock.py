from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools/stage_migraphx_for_therock.zsh"


def test_stage_migraphx_script_has_valid_zsh_syntax():
    subprocess.run(["zsh", "-n", str(SCRIPT)], check=True)


def test_stage_migraphx_script_help_documents_deploy_one_liner():
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "tools/stage_migraphx_for_therock.zsh --clean --deploy" in result.stdout
    assert "--skip-build" in result.stdout
    assert "--stage PATH" in result.stdout
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

    assert "-DMIGRAPHX_USE_COMPOSABLEKERNEL=$ck" in script
    assert "-DMIGRAPHX_ENABLE_MLIR=$mlir" in script
    assert "-DROCM_ENABLE_CLANG_TIDY=OFF" in script
