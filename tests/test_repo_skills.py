from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_local_workflow_skills_exclude_user_global_worktree_policy():
    agents = REPO_ROOT / "AGENTS.md"
    zsh_skill = REPO_ROOT / ".agents/skills/idiomatic-zsh/SKILL.md"
    rebuild_skill = REPO_ROOT / ".agents/skills/deploying-local-arch-packages/SKILL.md"
    inference_skill = REPO_ROOT / ".agents/skills/run-local-inference-scenarios/SKILL.md"
    worktree_skill = (
        REPO_ROOT / ".agents/skills/using-persistent-git-worktrees/SKILL.md"
    )

    assert agents.is_file()
    assert zsh_skill.is_file()
    assert rebuild_skill.is_file()
    assert inference_skill.is_file()
    assert not worktree_skill.exists()

    agents_text = agents.read_text(encoding="utf-8")
    zsh_text = zsh_skill.read_text(encoding="utf-8")
    rebuild_text = rebuild_skill.read_text(encoding="utf-8")
    inference_text = inference_skill.read_text(encoding="utf-8")

    assert "zsh" in zsh_text.lower()
    assert ".agents/skills/using-persistent-git-worktrees/SKILL.md" not in agents_text
    assert "<repo>.wt/<branch-or-task>" not in agents_text
    assert "tools/amerge" in rebuild_text
    assert "tools/run_inference_scenarios.py" in rebuild_text
    assert "docs/worklog/amerge" in rebuild_text
    assert "tools/run_inference_scenarios.py" in inference_text
    assert "tools/amerge" in inference_text
    assert "docs/worklog/inference-runs" in inference_text
