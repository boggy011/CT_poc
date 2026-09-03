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


def test_pdf_upload_through_the_form(app_for: Callable[[str], AppTest]):
    from pathlib import Path

    at = app_for(ANNA)
    select_starting_with(at, "account_id", "A1")
    at.run()
    fill_valid_form(at)
    at.file_uploader(key="att_delivery_note").upload("sample.pdf", Path("tests/fixtures/sample.pdf").read_bytes(), "application/pdf")
    at.file_uploader(key="att_other").upload("scanned.pdf", Path("tests/fixtures/scanned.pdf").read_bytes(), "application/pdf")
    at.button(key="FormSubmitter:intake-Submit request").click().run()
    assert not at.exception
    assert at.success
    assert any("no text layer" in w.value for w in at.warning)
    internal = Principal(email="ops1@abi.example", account_ids=frozenset(), role=Role.INTERNAL)
    newest = state.get_container().ports.submissions.list_submissions(internal)[0]
    assert [(m.doc_type, m.has_text_layer) for m in newest.attachments] == [("delivery_note", True), ("other", False)]
    assert newest.attachments[0].original_filename == "sample.pdf"


def test_non_pdf_upload_is_reported_not_crashed(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    select_starting_with(at, "account_id", "A1")
    at.run()
    fill_valid_form(at)
    at.file_uploader(key="att_delivery_note").upload("fake.pdf", b"GIF89a not a pdf", "application/pdf")
    at.button(key="FormSubmitter:intake-Submit request").click().run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "is not a PDF" in text


def test_submitted_result_does_not_leak_to_next_user(app_for: Callable[[str], AppTest]):
    from tests.ui.conftest import BRAM

    at = app_for(ANNA)
    select_starting_with(at, "account_id", "A1")
    at.run()
    fill_valid_form(at)
    at.text_input(key="f_bl_no").set_value("BL-ANNA-SECRET")
    at.button(key="FormSubmitter:intake-Submit request").click().run()
    assert at.success
    at.sidebar.selectbox(key="demo_user").select(BRAM).run()
    assert not at.exception
    rendered = " ".join(str(e.value) for e in list(at.markdown) + list(at.caption) + list(at.success))
    assert "BL-ANNA-SECRET" not in rendered and "A1" not in rendered
    assert not at.success
