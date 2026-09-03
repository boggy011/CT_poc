"""AppTest helpers."""

from datetime import date

from streamlit.testing.v1 import AppTest

SUBMIT_KEY = "FormSubmitter:intake-Submit Request"


def go(at: AppTest, page: str) -> AppTest:
    return at.sidebar.radio[0].set_value(page).run()


def select_starting_with(at: AppTest, key: str, prefix: str) -> None:
    box = at.selectbox(key=key)
    for i, option in enumerate(box.options):
        if str(option).startswith(prefix):
            box.select_index(i)
            return
    raise AssertionError(f"no option starting with {prefix!r} in {box.options}")


def fill_valid_form(at: AppTest) -> None:
    select_starting_with(at, "f_sku_code", "KEG50")
    at.text_input(key="f_container_no").set_value("1234567890")
    at.text_input(key="f_bl_no").set_value("BL-77")
    select_starting_with(at, "f_destination", "Antwerp")
    at.date_input(key="f_pickup_date").set_value(date(2026, 9, 10))
    at.number_input(key="f_quantity").set_value(12)
