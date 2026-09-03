"""Read-only rendering of one submission, shared by the customer and internal screens."""

from datetime import datetime

import streamlit as st

from retpack_core.fieldspec import FormSpec
from retpack_core.fold import Submission
from retpack_core.models import Status
from retpack_ui.theme import CUSTOMER_STATUS_LABELS, STATUS_LABELS


def short_ref(submission_id: str) -> str:
    """Human-friendly reference: last 12 characters of the id."""
    return submission_id[-12:].upper()


def customer_status(sub: Submission) -> str:
    """FR-07: customers see validated / not validated only."""
    return CUSTOMER_STATUS_LABELS[sub.status is not Status.SUBMITTED]


def internal_status(sub: Submission) -> str:
    """Human label for the internal status."""
    return STATUS_LABELS[sub.status]


def fmt_time(value: datetime) -> str:
    """Compact UTC timestamp."""
    return value.strftime("%Y-%m-%d %H:%M")


def render_values(sub: Submission, spec: FormSpec, *, show_original: bool = False) -> None:
    """Table of field label to current value, optionally with the original customer value."""
    rows = []
    for f in spec.fields:
        current = sub.values.get(f.name)
        row = {"Field": f.label, "Value": "" if current is None else str(current)}
        if show_original:
            original = sub.original_values.get(f.name)
            row["Original"] = "" if original is None else str(original)
            row["Changed"] = "Yes" if original != current else ""
        rows.append(row)
    st.dataframe(rows, hide_index=True, width="stretch")


def render_attachments(sub: Submission) -> None:
    """List attachments with the text-layer flag."""
    if not sub.attachments:
        st.caption("No documents attached.")
        return
    rows = [
        {
            "Document": m.original_filename,
            "Type": m.doc_type.replace("_", " ").capitalize(),
            "Pages": m.page_count,
            "Size (KB)": round(m.size_bytes / 1024, 1),
            "Readable text": "Yes" if m.has_text_layer else "No (scanned)",
        }
        for m in sub.attachments
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


def render_outcome(sub: Submission, *, internal: bool) -> None:
    """Credit note and, for internal users, the CPI outcome."""
    if sub.credit_note:
        st.info(
            f"Credit note {sub.credit_note.credit_note_no}: {sub.credit_note.outcome} ({fmt_time(sub.credit_note.recorded_at)})", icon=":material/receipt_long:"
        )
    if not internal:
        return
    if sub.cpi_reference:
        st.success(f"SAP return order {sub.cpi_reference}", icon=":material/check_circle:")
    if sub.cpi_error:
        (st.error if sub.status is Status.CPI_FAILED else st.warning)(f"SAP / CPI: {sub.cpi_error}", icon=":material/error:")


def render_audit(sub: Submission, spec: FormSpec) -> None:
    """Internal-only trail of overwrites (NFR-05)."""
    if not sub.overwrites:
        st.caption("No corrections so far.")
        return
    labels = {f.name: f.label for f in spec.fields}
    rows = [
        {
            "When": fmt_time(o.occurred_at),
            "By": o.actor,
            "Field": labels.get(o.field, o.field),
            "From": "" if o.prior is None else str(o.prior),
            "To": "" if o.new is None else str(o.new),
        }
        for o in sub.overwrites
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
