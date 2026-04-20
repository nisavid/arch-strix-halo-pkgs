from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_local_workflow_skills_exist_and_cross_reference():
    zsh_skill = REPO_ROOT / ".agents/skills/idiomatic-zsh/SKILL.md"
    rebuild_skill = REPO_ROOT / ".agents/skills/deploying-local-arch-packages/SKILL.md"
    inference_skill = REPO_ROOT / ".agents/skills/run-local-inference-scenarios/SKILL.md"

    assert zsh_skill.is_file()
    assert rebuild_skill.is_file()
    assert inference_skill.is_file()

    zsh_text = zsh_skill.read_text(encoding="utf-8")
    rebuild_text = rebuild_skill.read_text(encoding="utf-8")
    inference_text = inference_skill.read_text(encoding="utf-8")

    assert "zsh" in zsh_text.lower()
    assert "tools/amerge" in rebuild_text
    assert "tools/run_inference_scenarios.py" in rebuild_text
    assert "docs/worklog/amerge" in rebuild_text
    assert "tools/run_inference_scenarios.py" in inference_text
    assert "tools/amerge" in inference_text
    assert "docs/worklog/inference-runs" in inference_text
