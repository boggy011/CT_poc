"""Reference data from in-memory rows (loaded from JSON fixtures by the factory)."""

from collections.abc import Iterable

from retpack_core.errors import NotFoundError
from retpack_core.models import Account, KegBalance, SalesOrg, Sku
from retpack_core.principal import Principal


class InMemoryReferenceRepository:
    """List-backed ``ReferenceRepository`` with principal scoping."""

    def __init__(self, *, accounts: Iterable[Account], skus: Iterable[Sku], sales_orgs: Iterable[SalesOrg], balances: Iterable[KegBalance]) -> None:
        self._accounts = tuple(accounts)
        self._skus = tuple(skus)
        self._sales_orgs = tuple(sales_orgs)
        self._balances = {b.account_id: b for b in balances}

    def my_accounts(self, principal: Principal) -> tuple[Account, ...]:
        """See ``ReferenceRepository.my_accounts``."""
        if principal.is_scoped:
            return tuple(a for a in self._accounts if a.account_id in principal.account_ids)
        return self._accounts

    def skus_for_account(self, principal: Principal, account_id: str) -> tuple[Sku, ...]:
        """See ``ReferenceRepository.skus_for_account``."""
        self._require_account(principal, account_id)
        return tuple(s for s in self._skus if s.account_id == account_id)

    def sales_orgs(self, principal: Principal) -> tuple[SalesOrg, ...]:
        """See ``ReferenceRepository.sales_orgs``."""
        return self._sales_orgs

    def keg_balance(self, principal: Principal, account_id: str) -> KegBalance | None:
        """See ``ReferenceRepository.keg_balance``."""
        self._require_account(principal, account_id)
        return self._balances.get(account_id)

    @staticmethod
    def _require_account(principal: Principal, account_id: str) -> None:
        if principal.is_scoped and account_id not in principal.account_ids:
            raise NotFoundError(account_id)
