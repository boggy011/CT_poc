"""Read-side queries for both external screens and the internal queue."""

from typing import BinaryIO

from retpack_core.errors import NotFoundError
from retpack_core.fold import Submission
from retpack_core.models import KegBalance, Status
from retpack_core.ports import Ports
from retpack_core.principal import Principal


class QueryService:
    """Principal-scoped reads (FR-07, FR-08, FR-11)."""

    def __init__(self, ports: Ports) -> None:
        self._ports = ports

    def list_requests(self, principal: Principal, *, status: Status | None = None, limit: int = 200) -> tuple[Submission, ...]:
        """Requests visible to the principal, newest first."""
        return self._ports.submissions.list_submissions(principal, status=status, limit=limit)

    def get_request(self, principal: Principal, submission_id: str) -> Submission:
        """One request.

        Raises:
            NotFoundError: If unknown or outside the principal's scope.
        """
        return self._ports.submissions.get_submission(principal, submission_id)

    def keg_balances(self, principal: Principal) -> tuple[KegBalance, ...]:
        """Balances for every account the principal may see, where computed."""
        out = []
        for account in self._ports.reference.my_accounts(principal):
            balance = self._ports.reference.keg_balance(principal, account.account_id)
            if balance is not None:
                out.append(balance)
        return tuple(out)

    def open_attachment(self, principal: Principal, submission_id: str, *, seq: int) -> BinaryIO:
        """Open one stored PDF after confirming the principal may see its submission.

        Raises:
            NotFoundError: If the submission or attachment is not visible.
        """
        sub = self.get_request(principal, submission_id)
        for meta in sub.attachments:
            if meta.seq == seq:
                return self._ports.attachments.open(principal, meta)
        raise NotFoundError(f"attachment {seq} not found")
