"""Reference data rows served from Databricks views (read-only)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Account(BaseModel):
    """Customer account (payer / sold-to)."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    name: str
    sales_org: str


class Sku(BaseModel):
    """Returnable-packaging SKU available to one account."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    sku_code: str
    description: str


class SalesOrg(BaseModel):
    """Sales organisation."""

    model_config = ConfigDict(frozen=True)

    code: str
    name: str


class KegBalance(BaseModel):
    """Per-account shipped vs. returned balance, computed in Databricks."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    shipped: int
    returned: int
    as_of: datetime

    @property
    def balance(self) -> int:
        """Kegs still outstanding at the customer."""
        return self.shipped - self.returned
