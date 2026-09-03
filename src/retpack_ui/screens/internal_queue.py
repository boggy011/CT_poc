"""Internal screen: request queue, overwrite, validate."""

from collections.abc import Callable
from typing import Any

import streamlit as st

from retpack_adapters.factory import Container
from retpack_core.errors import ConcurrencyConflictError, NotFoundError, NotPermittedError, StateError, ValidationFailedError
from retpack_core.fold import Submission
from retpack_core.models import Status
from retpack_core.principal import Principal
from retpack_core.services import QueryService, ReviewService
from retpack_ui.components.detail import fmt_time, render_attachments, render_audit, render_outcome, render_values, short_ref
from retpack_ui.components.form_renderer import render_field

RESULT_KEY = "queue_result"
FLASH_KEY = "queue_flash"
SEEN_KEY = "queue_seen"
"""(submission_id, seq) as last rendered: actions use the version the user saw, not a fresh read."""
NEXT_STATUS_KEY = "queue_status_next"
"""Status filter to apply on the next run; widget state cannot be written after the widget is drawn."""
DOWNLOAD_KEY = "queue_download"
"""(submission_id, seq, filename, bytes) for at most one prepared download per session."""
STATUS_FILTERS = [*(s.value for s in Status), "All"]
_FLASH = {"success": st.success, "error": st.error, "warning": st.warning, "info": st.info}


def render(container: Container, principal: Principal) -> None:
    """Render the queue and the detail / action panel for the selected request."""
    st.title("Request queue")
    query = QueryService(container.ports)
    review = ReviewService(container.ports, container.spec)
    _flash()
    next_status = st.session_state.pop(NEXT_STATUS_KEY, None)
    if next_status is not None:
        st.session_state["queue_status"] = next_status

    chosen = st.selectbox("Status", STATUS_FILTERS, index=0, key="queue_status")
    subs = query.list_requests(principal, status=None if chosen == "All" else Status(chosen))
    if not subs:
        st.info("No requests in this status.")
        return
    st.dataframe(_rows(subs), hide_index=True, width="stretch")

    ids = [s.submission_id for s in subs]
    selected = st.selectbox("Open request", ids, index=None, format_func=short_ref, key="queue_selected", placeholder="Select a reference…")
    if selected is None:
        return
    sub = _current(query, principal, selected)
    if sub is None:
        return
    _render_detail(container, principal, query, review, sub)


def _rows(subs: tuple[Submission, ...]) -> list[dict[str, Any]]:
    return [
        {
            "Reference": short_ref(s.submission_id),
            "Account": s.account_id,
            "Customer": s.submitted_by,
            "SKU": s.values.get("sku_code", ""),
            "Quantity": s.values.get("quantity", ""),
            "Submitted": fmt_time(s.submitted_at),
            "Status": s.status.value,
            "PDFs": len(s.attachments),
            "Unreadable PDFs": sum(1 for m in s.attachments if not m.has_text_layer),
        }
        for s in subs
    ]


def _current(query: QueryService, principal: Principal, submission_id: str) -> Submission | None:
    cached: Submission | None = st.session_state.pop(RESULT_KEY, None)
    if cached is not None and cached.submission_id == submission_id:
        return cached
    try:
        return query.get_request(principal, submission_id)
    except NotFoundError:
        st.error("Request not found.")
        return None


def _seen_seq(sub: Submission) -> int:
    seen_id, seen_seq = st.session_state.get(SEEN_KEY, (None, 0))
    return int(seen_seq) if seen_id == sub.submission_id else sub.seq


def _render_detail(container: Container, principal: Principal, query: QueryService, review: ReviewService, sub: Submission) -> None:
    expected_seq = _seen_seq(sub)
    st.markdown(
        f"**Request {short_ref(sub.submission_id)}** · {sub.status.value} · {sub.account_id} · {sub.submitted_by} · submitted {fmt_time(sub.submitted_at)}"
    )
    st.caption(f"Full reference: {sub.submission_id} · version {sub.seq}")
    render_outcome(sub, internal=True)
    render_values(sub, container.spec, show_original=True)
    render_audit(sub, container.spec)
    render_attachments(sub)
    _render_downloads(query, principal, sub)
    if sub.status in {Status.SUBMITTED, Status.CPI_FAILED}:
        _render_actions(container, principal, review, sub, expected_seq)
    st.session_state[SEEN_KEY] = (sub.submission_id, sub.seq)


def _render_downloads(query: QueryService, principal: Principal, sub: Submission) -> None:
    """Two-step download so bytes are read once, on request, and at most one file is resident."""
    prepared = st.session_state.get(DOWNLOAD_KEY)
    for m in sub.attachments:
        col_prep, col_dl = st.columns([1, 3])
        if col_prep.button(f"Prepare {m.original_filename}", key=f"prep_{m.seq}"):
            with query.open_attachment(principal, sub.submission_id, seq=m.seq) as f:
                st.session_state[DOWNLOAD_KEY] = (sub.submission_id, m.seq, m.original_filename, f.read())
            st.rerun()
        if prepared and prepared[0] == sub.submission_id and prepared[1] == m.seq:
            col_dl.download_button(f"Download {prepared[2]}", data=prepared[3], file_name=prepared[2], mime="application/pdf", key=f"dl_{m.seq}")


def _render_actions(container: Container, principal: Principal, review: ReviewService, sub: Submission, expected_seq: int) -> None:
    st.subheader("Correct a field")
    labels = {f.name: f.label for f in container.spec.fields}
    names = list(review.correctable_fields())
    field_name = str(st.selectbox("Field", names, format_func=lambda n: labels[n], key="ow_field"))
    choices = review.enum_choices(principal, account_id=sub.account_id)
    new_value = render_field(container.spec.field(field_name), choices, key_prefix="ow_")
    col_ow, col_val = st.columns(2)
    if col_ow.button("Overwrite", key="overwrite"):
        _act(
            lambda: review.overwrite_field(principal, sub.submission_id, field=field_name, new_value=new_value, expected_seq=expected_seq),
            f"{labels[field_name]} updated.",
        )
    if col_val.button("Validate and release to SAP", key="validate", type="primary"):
        _act(lambda: review.validate(principal, sub.submission_id, expected_seq=expected_seq), "Request validated and queued for SAP.", keep_visible=True)


def _act(action: Callable[[], Submission], success: str, *, keep_visible: bool = False) -> None:
    try:
        st.session_state[RESULT_KEY] = action()
        st.session_state[FLASH_KEY] = ("success", success)
        if keep_visible:
            st.session_state[NEXT_STATUS_KEY] = "All"
    except ValidationFailedError as exc:
        st.session_state[FLASH_KEY] = ("error", "; ".join(f"{k}: {', '.join(v)}" for k, v in exc.errors.items()))
    except ConcurrencyConflictError:
        st.session_state[FLASH_KEY] = ("warning", "This request was changed by someone else. Review the latest version and try again.")
    except (StateError, NotPermittedError, NotFoundError) as exc:
        st.session_state[FLASH_KEY] = ("info", str(exc))
    st.rerun()


def _flash() -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        kind, message = flash
        _FLASH.get(kind, st.info)(message)
