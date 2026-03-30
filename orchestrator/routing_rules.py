from __future__ import annotations

WORKFLOW_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "initialized": ("planning",),
    "planning": ("retrieve", "generation", "failed"),
    "retrieve": ("validation", "generation", "planning", "failed"),
    "generation": ("validation", "alignment", "critic", "failed"),
    "alignment": ("critic", "failed"),
    "critic": ("validation", "refinement", "failed"),
    "validation": ("alignment", "critic", "refinement", "planning", "finalized", "failed"),
    "refinement": ("alignment", "critic", "failed"),
    "finalized": (),
    "failed": (),
}


def can_transition(current_stage: str, next_stage: str) -> bool:
    if next_stage in {"finalized", "failed"}:
        return True
    return next_stage in WORKFLOW_TRANSITIONS.get(current_stage, ())
