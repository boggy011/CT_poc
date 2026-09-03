"""External screen 1: new return request."""

import streamlit as st

from retpack_adapters.factory import Container
from retpack_core.errors import InvalidAttachmentError, NotPermittedError, ValidationFailedError
from retpack_core.principal import Principal
from retpack_core.services import IntakeResult, IntakeService
from retpack_ui.components.attachment_uploader import render_uploaders
from retpack_ui.components.detail import render_attachments, render_values, short_ref
from retpack_ui.components.form_renderer import clear_form_state, render_form

RESULT_KEY = "intake_result"
ACCOUNT_KEY = "account_id"


def render(container: Container, principal: Principal) -> None:
    """Render the intake form and, after submit, the result built from the returned object."""
    st.title("New return request")
    intake = IntakeService(container.ports, container.spec, container.policy)
    spec = container.spec

    result: IntakeResult | None = st.session_state.get(RESULT_KEY)
    if result is not None:
        _render_result(container, result)
        if st.button("Start another request", key="another"):
            st.session_state.pop(RESULT_KEY, None)
            clear_form_state(spec, extra_keys=(ACCOUNT_KEY,))
            st.rerun()
        return

    account_field = spec.account_field
    account_id: str | None = None
    if account_field is not None:
        choices = intake.enum_choices(principal, account_id=None).get(account_field.name, ())
        labels = {c.value: c.label for c in choices}
        account_id = st.selectbox(
            f"{account_field.label} *", [c.value for c in choices], index=None, format_func=lambda v: labels[v], key=ACCOUNT_KEY, placeholder="Select…"
        )

    choices_all = intake.enum_choices(principal, account_id=account_id)
    with st.form("intake"):
        values = render_form(spec, choices_all, skip=frozenset({account_field.name}) if account_field else frozenset())
        uploads = render_uploaders(container.policy)
        submitted = st.form_submit_button("Submit request", type="primary")
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
        st.error(f"Request not accepted: {exc}")
        return
    st.rerun()


def _render_errors(container: Container, exc: ValidationFailedError) -> None:
    labels = {f.name: f.label for f in container.spec.fields}
    labels.update({f"attachments.{d.name}": d.label for d in container.policy.doc_types})
    labels["attachments"] = "Documents"
    st.error("Please correct the following and submit again:")
    for name, messages in exc.errors.items():
        st.markdown(f"- **{labels.get(name, name)}**: {', '.join(messages)}")


def _render_result(container: Container, result: IntakeResult) -> None:
    sub = result.submission
    st.success(f"Request {short_ref(sub.submission_id)} submitted. Status: not validated. The ABI team will review it.")
    for warning in result.warnings:
        st.warning(warning)
    st.caption(f"Full reference: {sub.submission_id}")
    render_values(sub, container.spec)
    render_attachments(sub)
