from dataclasses import dataclass
from typing import Protocol


class PublishConflict(Exception):
    """WordPress changed since the proposal was created."""


class PublishNotApproved(Exception):
    """The proposal has not received explicit approval."""


class RollbackNotConfirmed(Exception):
    """Rollback requires explicit confirmation."""


class PublishingClient(Protocol):
    def current_state(self, object_id: int) -> dict: ...

    def apply_change(self, object_id: int, payload: dict) -> dict: ...


@dataclass(frozen=True)
class MutationResult:
    mutation_type: str
    before_value: object
    after_value: object
    content_hash: str
    response: dict


class Publisher:
    def __init__(self, wordpress: PublishingClient) -> None:
        self.wordpress = wordpress

    def publish(self, proposal) -> MutationResult:
        if proposal.approval_state != "approved":
            raise PublishNotApproved("Proposal must be approved before publishing")
        current = self.wordpress.current_state(proposal.wordpress_object_id)
        if current["content_hash"] != proposal.base_content_hash:
            raise PublishConflict("WordPress content changed after proposal creation")
        current_value = current.get("values", {}).get(proposal.change_type)
        if current_value != proposal.before_value:
            raise PublishConflict("Proposed before value does not match WordPress")
        response = self.wordpress.apply_change(
            proposal.wordpress_object_id,
            {
                "change_type": proposal.change_type,
                "value": proposal.after_value,
                "expected_content_hash": proposal.base_content_hash,
            },
        )
        return MutationResult(
            mutation_type="publish",
            before_value=proposal.before_value,
            after_value=proposal.after_value,
            content_hash=response["content_hash"],
            response=response,
        )

    def rollback(
        self,
        proposal,
        published: MutationResult,
        *,
        confirmed: bool,
    ) -> MutationResult:
        if not confirmed:
            raise RollbackNotConfirmed("Rollback requires confirmation")
        current = self.wordpress.current_state(proposal.wordpress_object_id)
        if current["content_hash"] != published.content_hash:
            raise PublishConflict("WordPress content changed after publication")
        response = self.wordpress.apply_change(
            proposal.wordpress_object_id,
            {
                "change_type": proposal.change_type,
                "value": published.before_value,
                "expected_content_hash": published.content_hash,
            },
        )
        return MutationResult(
            mutation_type="rollback",
            before_value=published.after_value,
            after_value=published.before_value,
            content_hash=response["content_hash"],
            response=response,
        )
