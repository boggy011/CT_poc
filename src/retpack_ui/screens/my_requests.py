"""External screen 2: my requests, status, credit note, keg balance."""

import streamlit as st

from retpack_adapters.factory import Container
from retpack_core.principal import Principal
from retpack_core.services import QueryService
from retpack_ui.components.detail import customer_status, fmt_time, render_attachments, render_outcome, render_values, short_ref
from retpack_ui.theme import customer_status_badge, page_header, section


def render(container: Container, principal: Principal) -> None:
    """Render balances, the request list and a read-only detail."""
    page_header("My Requests", "Every return request you have submitted, its validation status and the credit note once issued.")
    query = QueryService(container.ports)
    _render_balances(query, principal)

    subs = query.list_requests(principal)
    with section("Requests", "Newest first. Customers see two statuses: not validated (waiting for the ABI team) and validated (released to SAP)."):
        if not subs:
            st.info("No requests yet. Use New Request to report a return shipment.", icon=":material/info:")
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
    with section(f"Request {short_ref(sub.submission_id)}", f"Submitted {fmt_time(sub.submitted_at)} for account {sub.account_id}"):
        customer_status_badge(sub.status)
        render_outcome(sub, internal=False)
        tab_values, tab_docs = st.tabs(["Details", "Documents"])
        with tab_values:
            render_values(sub, container.spec)
        with tab_docs:
            render_attachments(sub)


def _render_balances(query: QueryService, principal: Principal) -> None:
    names = {a.account_id: a.name for a in query.accounts(principal)}
    balances = query.keg_balances(principal)
    with section("Keg Balance", "Kegs shipped to you minus kegs returned, as calculated by ABI. For detail, contact your ABI representative."):
        if not balances:
            st.caption("No balance available yet.")
            return
        for col, b in zip(st.columns(max(len(balances), 3)), balances, strict=False):
            col.metric(
                f"{names.get(b.account_id, b.account_id)} ({b.account_id})",
                b.balance,
                help=f"Shipped {b.shipped}, returned {b.returned}, as of {b.as_of.date()}",
            )
