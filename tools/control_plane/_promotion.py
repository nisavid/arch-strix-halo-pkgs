"""Promotion admission across evidence semantics and authority provenance."""

from __future__ import annotations

from ._authority import require_promotable
from ._evaluation import (
    EvidenceEvaluation,
    PromotionAssessment,
    require_promotable_evidence,
)


def admit_promotion(
    evaluation: EvidenceEvaluation,
    evidence_view: object,
) -> PromotionAssessment:
    """Admit one evaluation only when semantics and authority both pass.

    The authority proof is checked first. A structurally passing evaluation is
    never returned to a promotion caller when its evidence came from a fake or
    otherwise unverified adapter.
    """

    require_promotable(evidence_view)
    return require_promotable_evidence(evaluation)
