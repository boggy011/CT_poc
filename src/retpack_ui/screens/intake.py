"""External screen 1: new return request."""

import streamlit as st

from retpack_adapters.factory import Container
from retpack_core.errors import InvalidAttachmentError, NotPermittedError, ValidationFailedError
from retpack_core.principal import Principal
from retpack_core.services import IntakeResult, IntakeService
from retpack_ui.components.attachment_uploader import render_uploaders
from retpack_ui.components.detail import render_attachments, render_values, short_ref
from retpack_ui.components.form_renderer import clear_form_state, render_field
from retpack_ui.theme import page_header, section

RESULT_KEY = "intake_result"
ACCOUNT_KEY = "account_id"
SUBMIT_LABEL = "Submit Request"


def render(container: Container, principal: Principal) -> None:
    """Render the intake form and, after submit, the result built from the returned object."""
    page_header(
        "New Request", "Report a return shipment of empty kegs. Fields marked with * are required; the ABI team validates every request before it reaches SAP."
    )
    intake = IntakeService(container.ports, container.spec, container.policy)
    spec = container.spec

    result: IntakeResult | None = st.session_state.get(RESULT_KEY)
    if result is not None:
        _render_result(container, result)
        if st.button("Start Another Request", key="another", icon=":material/add:"):
            st.session_state.pop(RESULT_KEY, None)
            clear_form_state(spec, extra_keys=(ACCOUNT_KEY,))
            st.rerun()
        return

    account_field = spec.account_field
    account_id: str | None = None
    if account_field is not None:
        with section("Customer Account", "Which of your accounts is this return for? The packaging types below depend on it."):
            choices = intake.enum_choices(principal, account_id=None).get(account_field.name, ())
            labels = {c.value: c.label for c in choices}
            account_id = st.selectbox(
                f"{account_field.label} *", [c.value for c in choices], index=None, format_func=lambda v: labels[v], key=ACCOUNT_KEY, placeholder="Select…"
            )

    choices_all = intake.enum_choices(principal, account_id=account_id)
    skip = {account_field.name} if account_field else set()
    with st.form("intake"):
        values = {}
        for sec in spec.sections:
            fields = [f for f in spec.fields_in(sec.name) if f.name not in skip]
            if not fields:
                continue
            with section(sec.label):
                cols = st.columns(2)
                for i, f in enumerate(fields):
                    with cols[i % 2] if f.type.value != "text" else st.container():
                        values[f.name] = render_field(f, choices_all)
        with section(
            "Documents", f"PDF only, up to {container.policy.max_size_mb} MB each. Scanned PDFs are accepted but cannot be read by the automated cross-check."
        ):
            uploads = render_uploaders(container.policy)
        submitted = st.form_submit_button(SUBMIT_LABEL, type="primary", icon=":material/send:")
    if not submitted:
        return
    if account_field is not None:
        values[account_field.name] = account_id
    try:
        st.session_state[RESULT_KEY] = intake.submit(principal, values, uploads)
    except ValidationFailedError as exc:
        _render_errors(container, exc)
        return
    except (InvalidAttachmentError, NotPermittedError) as exc:
        st.error(f"Request not accepted: {exc}", icon=":material/block:")
        return
    st.rerun()


def _render_errors(container: Container, exc: ValidationFailedError) -> None:
    labels = {f.name: f.label for f in container.spec.fields}
    labels.update({f"attachments.{d.name}": d.label for d in container.policy.doc_types})
    labels["attachments"] = "Documents"
    st.error("Please correct the following and submit again:", icon=":material/error:")
    for name, messages in exc.errors.items():
        st.markdown(f"- **{labels.get(name, name)}**: {', '.join(messages)}")


def _render_result(container: Container, result: IntakeResult) -> None:
    sub = result.submission
    with section("Request Submitted"):
        left, right = st.columns([1, 2])
        left.metric("Reference", short_ref(sub.submission_id))
        right.success(
            "Your request has been received and is waiting for validation by the ABI team. You will see it under My Requests.", icon=":material/check_circle:"
        )
        for warning in result.warnings:
            st.warning(warning, icon=":material/visibility_off:")
        st.caption(f"Full reference: {sub.submission_id}")
    with section("What You Sent"):
        render_values(sub, container.spec)
    with section("Documents"):
        render_attachments(sub)
