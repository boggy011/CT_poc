"""External screen 2: my requests, status, credit note, keg balance."""

import streamlit as st

from retpack_adapters.factory import Container
from retpack_core.principal import Principal
from retpack_core.services import QueryService
from retpack_ui.components.detail import customer_status, fmt_time, render_attachments, render_outcome, render_values, short_ref


def render(container: Container, principal: Principal) -> None:
    """Render balances, the request list and a read-only detail."""
    st.title("My requests")
    query = QueryService(container.ports)
    _render_balances(container, principal, query)

    subs = query.list_requests(principal)
    st.subheader("Requests")
    if not subs:
        st.info("No requests yet.")
        return
    rows = [
        {
            "Reference": short_ref(s.submission_id),
            "Account": s.account_id,
            "SKU": s.values.get("sku_code", ""),
            "Quantity": s.values.get("quantity", ""),
            "Submitted": fmt_time(s.submitted_at),
            "Status": customer_status(s),
            "Credit note": s.credit_note.credit_note_no if s.credit_note else "",
        }
        for s in subs
    ]
    st.dataframe(rows, hide_index=True, width="stretch")

    ids = [s.submission_id for s in subs]
    selected = st.selectbox("Open request", ids, index=None, format_func=short_ref, key="my_selected", placeholder="Select a reference…")
    if selected is None:
        return
    sub = next(s for s in subs if s.submission_id == selected)
    st.markdown(f"**Request {short_ref(sub.submission_id)}** · {customer_status(sub)} · submitted {fmt_time(sub.submitted_at)}")
    render_outcome(sub, internal=False)
    render_values(sub, container.spec)
    render_attachments(sub)


def _render_balances(container: Container, principal: Principal, query: QueryService) -> None:
    st.subheader("Keg balance")
    names = {a.account_id: a.name for a in container.ports.reference.my_accounts(principal)}
    balances = query.keg_balances(principal)
    if not balances:
        st.caption("No balance available yet.")
        return
    for col, b in zip(st.columns(len(balances)), balances, strict=False):
        col.metric(
            f"{names.get(b.account_id, b.account_id)} ({b.account_id})", b.balance, help=f"Shipped {b.shipped}, returned {b.returned}, as of {b.as_of.date()}"
        )
