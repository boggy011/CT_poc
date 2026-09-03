"""Resolve ``ref:`` dropdown sources through the reference repository."""

from dataclasses import dataclass

from retpack_core.errors import NotFoundError
from retpack_core.fieldspec import FormSpec
from retpack_core.ports import ReferenceRepository
from retpack_core.principal import Principal


@dataclass(frozen=True)
class Choice:
    """One dropdown option."""

    value: str
    label: str


def enum_choices(reference: ReferenceRepository, spec: FormSpec, principal: Principal, *, account_id: str | None) -> dict[str, tuple[Choice, ...]]:
    """Labelled options for every enum field in ``spec``, scoped to ``principal``.

    Args:
        reference: Reference repository.
        spec: Form specification.
        principal: Caller; account-scoped sources are filtered to their accounts.
        account_id: Selected account for account-dependent sources; None yields
            no options for those.
    """
    out: dict[str, tuple[Choice, ...]] = {}
    for f in spec.fields:
        if f.static_options:
            out[f.name] = tuple(Choice(o, o) for o in f.static_options)
        elif f.ref_source is not None:
            out[f.name] = _resolve(reference, principal, f.ref_source, account_id)
    return out


def enum_options(reference: ReferenceRepository, spec: FormSpec, principal: Principal, *, account_id: str | None) -> dict[str, tuple[str, ...]]:
    """Same as ``enum_choices`` but values only, as the validator expects."""
    return {name: tuple(c.value for c in choices) for name, choices in enum_choices(reference, spec, principal, account_id=account_id).items()}


def _resolve(reference: ReferenceRepository, principal: Principal, source: str, account_id: str | None) -> tuple[Choice, ...]:
    if source == "my_accounts":
        return tuple(Choice(a.account_id, f"{a.account_id} - {a.name}") for a in reference.my_accounts(principal))
    if source == "sales_orgs":
        return tuple(Choice(s.code, f"{s.code} - {s.name}") for s in reference.sales_orgs(principal))
    if source == "skus_for_account":
        if account_id is None:
            return ()
        try:
            return tuple(Choice(s.sku_code, f"{s.sku_code} - {s.description}") for s in reference.skus_for_account(principal, account_id))
        except NotFoundError:
            return ()
    raise ValueError(f"unknown ref source {source!r}")
