from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTEXT = REPO_ROOT / "docs/architecture/convergence-domain.md"
ARCHITECTURE = REPO_ROOT / "docs/architecture/convergence-control-plane.md"
DOC_INDEX = REPO_ROOT / "docs/README.md"
CURRENT_STATE = REPO_ROOT / "docs/maintainers/current-state.md"
AGENTS = REPO_ROOT / "AGENTS.md"


def test_control_plane_language_and_architecture_are_durable():
    context = CONTEXT.read_text(encoding="utf-8")
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    normalized_architecture = " ".join(architecture.split())

    assert "**Attestation**" in context
    assert "**Evaluation**" in context
    assert "**Promotional evidence**" in context
    assert "content-addressed record proves identity and integrity" in architecture
    assert "canonical record core" in normalized_architecture
    assert "named recovery-successor execution" in normalized_architecture
    assert "currency is orthogonal" in normalized_architecture
    assert "does not turn the repository into a production authority" in architecture


def test_control_plane_docs_are_indexed_and_agent_routed():
    doc_index = DOC_INDEX.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")

    assert "architecture/convergence-control-plane.md" in doc_index
    assert "docs/architecture/convergence-control-plane.md" in agents


def test_current_state_keeps_repository_and_production_gates_distinct():
    current_state = CURRENT_STATE.read_text(encoding="utf-8")
    normalized = " ".join(current_state.split())

    assert "Repository control schemas" in current_state
    assert "nonpromotional" in current_state
    assert "operator-approved production substrate topology remains open" in normalized
