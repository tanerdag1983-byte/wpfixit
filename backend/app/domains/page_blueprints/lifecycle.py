from typing import Literal

BLUEPRINT_LIFECYCLE_STATES = (
    "capture_required",
    "capturing",
    "ready",
    "stale",
    "invalid",
)

BlueprintLifecycleState = Literal[
    "capture_required",
    "capturing",
    "ready",
    "stale",
    "invalid",
]


def blueprint_lifecycle_state_check(column_name: str = "state") -> str:
    allowed_values = ", ".join(repr(state) for state in BLUEPRINT_LIFECYCLE_STATES)
    return f"{column_name} IN ({allowed_values})"
