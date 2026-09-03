"""Read-only reference data from Databricks views (not swappable)."""

from typing import Protocol

from retpack_core.models import Account, KegBalance, SalesOrg, Sku
from retpack_core.principal import Principal


class ReferenceRepository(Protocol):
    """Reference lookups, filtered to the principal's accounts when scoped."""

    def my_accounts(self, principal: Principal) -> tuple[Account, ...]:
        """Accounts the principal may submit for (all accounts for unscoped principals)."""
        ...

    def skus_for_account(self, principal: Principal, account_id: str) -> tuple[Sku, ...]:
        """SKUs of one account.

        Raises:
            NotFoundError: If the account is outside the principal's scope.
        """
        ...

    def sales_orgs(self, principal: Principal) -> tuple[SalesOrg, ...]:
        """All sales organisations (global reference data)."""
        ...

    def keg_balance(self, principal: Principal, account_id: str) -> KegBalance | None:
        """Current keg balance for one account, or None if not computed yet.

        Raises:
            NotFoundError: If the account is outside the principal's scope.
        """
        ...
