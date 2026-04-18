from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_REPO_DOC = REPO_ROOT / "docs/usage/local-repo.md"
CURRENT_STATE = REPO_ROOT / "docs/maintainers/current-state.md"
BACKLOG = REPO_ROOT / "docs/backlog.md"


def test_old_patch_audit_wrapper_is_removed():
    assert not (REPO_ROOT / "tools/run_patch_audit_host_checks.sh").exists()


def test_docs_reference_new_rebuild_and_inference_entrypoints():
    local_repo = LOCAL_REPO_DOC.read_text(encoding="utf-8")
    current_state = CURRENT_STATE.read_text(encoding="utf-8")
    backlog = BACKLOG.read_text(encoding="utf-8")

    assert "tools/rebuild_publish_install.zsh" in local_repo
    assert "tools/run_inference_scenarios.py" in local_repo
    assert "tools/run_patch_audit_host_checks.sh" not in local_repo
    assert "tools/run_inference_scenarios.py" in current_state
    assert "Qwen3.5" in backlog
