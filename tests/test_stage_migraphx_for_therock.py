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
