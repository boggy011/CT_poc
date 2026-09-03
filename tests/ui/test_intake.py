from collections.abc import Callable

from streamlit.testing.v1 import AppTest

from retpack_core.principal import Principal, Role
from retpack_ui import state
from tests.ui.conftest import ANNA
from tests.ui.helpers import fill_valid_form, select_starting_with


def test_required_errors_shown(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    select_starting_with(at, "account_id", "A1")
    at.run()
    at.button(key="FormSubmitter:intake-Submit request").click().run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Container number" in text and "required" in text
    assert "Please correct" in at.error[0].value


def test_format_error_shown(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    select_starting_with(at, "account_id", "A1")
    at.run()
    fill_valid_form(at)
    at.text_input(key="f_container_no").set_value("12")
    at.button(key="FormSubmitter:intake-Submit request").click().run()
    text = " ".join(m.value for m in at.markdown)
    assert r"must match ^\d{10}$" in text


def test_valid_submit_shows_reference_and_persists(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    select_starting_with(at, "account_id", "A1")
    at.run()
    fill_valid_form(at)
    at.button(key="FormSubmitter:intake-Submit request").click().run()
    assert not at.exception
    assert at.success and "submitted" in at.success[0].value
    internal = Principal(email="ops1@abi.example", account_ids=frozenset(), role=Role.INTERNAL)
    newest = state.get_container().ports.submissions.list_submissions(internal)[0]
    assert newest.submitted_by == ANNA and newest.values["container_no"] == "1234567890" and newest.values["quantity"] == 12
    assert newest.submission_id[-12:].upper() in at.success[0].value
    # "Start another request" clears the result panel and shows the form again.
    at.button(key="another").click().run()
    assert not at.success
    assert at.selectbox(key="account_id")


def test_sku_options_depend_on_selected_account(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    select_starting_with(at, "account_id", "A2")
    at.run()
    assert any(str(o).startswith("KEG10") for o in at.selectbox(key="f_sku_code").options)
    select_starting_with(at, "account_id", "A1")
    at.run()
    assert not any(str(o).startswith("KEG10") for o in at.selectbox(key="f_sku_code").options)


def test_without_account_selected_no_skus_and_submit_fails(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    assert at.selectbox(key="f_sku_code").options == []
    at.button(key="FormSubmitter:intake-Submit request").click().run()
    text = " ".join(m.value for m in at.markdown)
    assert "Account" in text and "required" in text
