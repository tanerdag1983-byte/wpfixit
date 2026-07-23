import json
from datetime import UTC, datetime

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.domains.page_packages.models import PageProposalStage

STAGE_NAMES = ("template", "text", "validation")
MAX_STAGE_RESULT_BYTES = 100_000
MAX_STAGE_ERRORS_BYTES = 20_000

ALLOWED_TRANSITIONS = {
    "pending": {"running"},
    "running": {"ready", "attention", "failed"},
    "attention": {"running"},
    "failed": {"running"},
    "ready": set(),
}


def initialize_proposal_stages(
    session: Session,
    proposal_version_id: str,
) -> list[PageProposalStage]:
    items = [
        PageProposalStage(
            proposal_version_id=proposal_version_id,
            name=name,
            state="pending",
            result={},
            errors={},
        )
        for name in STAGE_NAMES
    ]
    session.add_all(items)
    return items


def ordered_proposal_stages(
    session: Session,
    proposal_version_id: str,
) -> list[PageProposalStage]:
    ordering = case(
        {name: position for position, name in enumerate(STAGE_NAMES)},
        value=PageProposalStage.name,
        else_=len(STAGE_NAMES),
    )
    return list(
        session.scalars(
            select(PageProposalStage)
            .where(PageProposalStage.proposal_version_id == proposal_version_id)
            .order_by(ordering)
        ).all()
    )


def locked_stage(
    session: Session,
    proposal_version_id: str,
    stage_name: str,
) -> PageProposalStage:
    item = session.scalar(
        select(PageProposalStage)
        .where(
            PageProposalStage.proposal_version_id == proposal_version_id,
            PageProposalStage.name == stage_name,
        )
        .with_for_update()
    )
    if item is None:
        raise ValueError("stage_not_found")
    return item


def begin_stage(
    session: Session,
    proposal_version_id: str,
    stage_name: str,
) -> PageProposalStage:
    item = locked_stage(session, proposal_version_id, stage_name)
    _transition(item, "running")
    item.started_at = datetime.now(UTC)
    item.completed_at = None
    item.result = {}
    item.errors = {}
    return item


def complete_stage(
    session: Session,
    proposal_version_id: str,
    stage_name: str,
    *,
    result: dict,
) -> PageProposalStage:
    _validate_json("result", result, MAX_STAGE_RESULT_BYTES)
    item = locked_stage(session, proposal_version_id, stage_name)
    _transition(item, "ready")
    item.result = result
    item.errors = {}
    item.completed_at = datetime.now(UTC)
    return item


def attention_stage(
    session: Session,
    proposal_version_id: str,
    stage_name: str,
    *,
    errors: dict,
    result: dict | None = None,
) -> PageProposalStage:
    _validate_json("errors", errors, MAX_STAGE_ERRORS_BYTES)
    if result is not None:
        _validate_json("result", result, MAX_STAGE_RESULT_BYTES)
    item = locked_stage(session, proposal_version_id, stage_name)
    _transition(item, "attention")
    item.result = result or {}
    item.errors = errors
    item.completed_at = datetime.now(UTC)
    return item


def fail_stage(
    session: Session,
    proposal_version_id: str,
    stage_name: str,
    *,
    errors: dict,
) -> PageProposalStage:
    _validate_json("errors", errors, MAX_STAGE_ERRORS_BYTES)
    item = locked_stage(session, proposal_version_id, stage_name)
    _transition(item, "failed")
    item.errors = errors
    item.completed_at = datetime.now(UTC)
    return item


def retry_stage(
    session: Session,
    proposal_version_id: str,
    stage_name: str,
) -> PageProposalStage:
    item = locked_stage(session, proposal_version_id, stage_name)
    if item.state not in {"attention", "failed"}:
        raise ValueError("stage_not_retryable")
    _transition(item, "running")
    now = datetime.now(UTC)
    item.retry_count += 1
    item.started_at = now
    item.last_retried_at = now
    item.completed_at = None
    item.result = {}
    item.errors = {}
    return item


def _transition(item: PageProposalStage, target_state: str) -> None:
    if target_state not in ALLOWED_TRANSITIONS.get(item.state, set()):
        raise ValueError("invalid_stage_transition")
    item.state = target_state


def _validate_json(name: str, value: dict, limit: int) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"stage_{name}_must_be_object")
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(encoded) > limit:
        raise ValueError(f"stage_{name}_too_large")
