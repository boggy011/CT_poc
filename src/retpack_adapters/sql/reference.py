"""Read-only reference data and the email directory over SQL views/tables."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from retpack_adapters.sql.executor import SqlExecutor, check_identifier
from retpack_core.errors import NotFoundError
from retpack_core.models import Account, KegBalance, SalesOrg, Sku
from retpack_core.principal import Principal


@dataclass(frozen=True)
class ReferenceTables:
    """Qualified names of the ABI-owned reference views (ASSUMED until input 4; see docs/data_contract.md)."""

    account: str = "ref_account"
    sku: str = "ref_sku"
    sales_org: str = "ref_sales_org"
    email_account: str = "ref_email_account"
    internal_user: str = "ref_internal_user"
    keg_balance: str = "keg_balance"

    def __post_init__(self) -> None:
        """Validate every interpolated name."""
        for name in (self.account, self.sku, self.sales_org, self.email_account, self.internal_user, self.keg_balance):
            check_identifier(name)

    @classmethod
    def in_schema(cls, prefix: str) -> "ReferenceTables":
        """All default names under ``prefix`` (``catalog.schema`` or ``schema``)."""
        base = cls()
        return cls(**{k: f"{prefix}.{v}" for k, v in vars(base).items()})


class SqlReferenceRepository:
    """``ReferenceRepository`` with scoping in the SQL."""

    def __init__(self, executor: SqlExecutor, tables: ReferenceTables | None = None) -> None:
        self._db = executor
        self._t = tables or ReferenceTables()

    def my_accounts(self, principal: Principal) -> tuple[Account, ...]:
        """See ``ReferenceRepository.my_accounts``."""
        sql = f"SELECT account_id, name, sales_org FROM {self._t.account}"
        params: list[Any] = []
        if principal.is_scoped:
            if not principal.account_ids:
                return ()
            ids = sorted(principal.account_ids)
            sql += f" WHERE account_id IN ({', '.join('?' for _ in ids)})"
            params = ids
        return tuple(Account(account_id=str(a), name=str(n), sales_org=str(s)) for a, n, s in self._db.query(sql + " ORDER BY account_id", params))

    def skus_for_account(self, principal: Principal, account_id: str) -> tuple[Sku, ...]:
        """See ``ReferenceRepository.skus_for_account``."""
        _require_account(principal, account_id)
        rows = self._db.query(f"SELECT account_id, sku_code, description FROM {self._t.sku} WHERE account_id = ? ORDER BY sku_code", [account_id])
        return tuple(Sku(account_id=str(a), sku_code=str(c), description=str(d)) for a, c, d in rows)

    def sales_orgs(self, principal: Principal) -> tuple[SalesOrg, ...]:
        """See ``ReferenceRepository.sales_orgs``."""
        return tuple(SalesOrg(code=str(c), name=str(n)) for c, n in self._db.query(f"SELECT code, name FROM {self._t.sales_org} ORDER BY code"))

    def keg_balance(self, principal: Principal, account_id: str) -> KegBalance | None:
        """See ``ReferenceRepository.keg_balance``."""
        _require_account(principal, account_id)
        rows = self._db.query(f"SELECT account_id, shipped, returned, as_of FROM {self._t.keg_balance} WHERE account_id = ?", [account_id])
        if not rows:
            return None
        a, shipped, returned, as_of = rows[0]
        return KegBalance(account_id=str(a), shipped=int(shipped), returned=int(returned), as_of=_to_datetime(as_of))


class SqlAccountDirectory:
    """``AccountDirectory`` over the email mapping views."""

    def __init__(self, executor: SqlExecutor, tables: ReferenceTables | None = None) -> None:
        self._db = executor
        self._t = tables or ReferenceTables()

    def account_ids_for_email(self, email: str) -> frozenset[str]:
        """See ``AccountDirectory.account_ids_for_email``."""
        rows = self._db.query(f"SELECT account_id FROM {self._t.email_account} WHERE LOWER(email) = ?", [email.strip().lower()])
        return frozenset(str(r[0]) for r in rows)

    def is_internal(self, email: str) -> bool:
        """See ``AccountDirectory.is_internal``."""
        rows = self._db.query(f"SELECT 1 FROM {self._t.internal_user} WHERE LOWER(email) = ?", [email.strip().lower()])
        return bool(rows)


def _require_account(principal: Principal, account_id: str) -> None:
    if principal.is_scoped and account_id not in principal.account_ids:
        raise NotFoundError(account_id)


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value))
