from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_local_workflow_skills_exist_and_cross_reference():
    agents = REPO_ROOT / "AGENTS.md"
    zsh_skill = REPO_ROOT / ".agents/skills/idiomatic-zsh/SKILL.md"
    worktree_skill = (
        REPO_ROOT / ".agents/skills/using-persistent-git-worktrees/SKILL.md"
    )
    rebuild_skill = REPO_ROOT / ".agents/skills/deploying-local-arch-packages/SKILL.md"
    inference_skill = REPO_ROOT / ".agents/skills/run-local-inference-scenarios/SKILL.md"

    assert agents.is_file()
    assert zsh_skill.is_file()
    assert worktree_skill.is_file()
    assert rebuild_skill.is_file()
    assert inference_skill.is_file()

    agents_text = agents.read_text(encoding="utf-8")
    zsh_text = zsh_skill.read_text(encoding="utf-8")
    worktree_text = worktree_skill.read_text(encoding="utf-8")
    rebuild_text = rebuild_skill.read_text(encoding="utf-8")
    inference_text = inference_skill.read_text(encoding="utf-8")

    assert "zsh" in zsh_text.lower()
    assert ".agents/skills/using-persistent-git-worktrees/SKILL.md" in agents_text
    assert "<repo>.wt/<branch-or-task>" in agents_text
    assert "request escalation" in agents_text
    assert "/tmp" in agents_text
    assert "<repo>.wt/<branch-or-task>" in worktree_text
    assert "request escalation" in worktree_text
    assert "/tmp" in worktree_text
    assert "git worktree add" in worktree_text
    assert "tools/amerge" in rebuild_text
    assert "tools/run_inference_scenarios.py" in rebuild_text
    assert "docs/worklog/amerge" in rebuild_text
    assert "tools/run_inference_scenarios.py" in inference_text
    assert "tools/amerge" in inference_text
    assert "docs/worklog/inference-runs" in inference_text
