from collections.abc import Callable

from streamlit.testing.v1 import AppTest

from tests.ui.conftest import ANNA, OPS


def test_customer_sees_two_pages(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    assert not at.exception
    nav = at.sidebar.radio[0]
    assert nav.options == ["New request", "My requests"]
    assert ANNA in "".join(c.value for c in at.sidebar.caption)


def test_internal_sees_one_page(app_for: Callable[[str], AppTest]):
    at = app_for(OPS)
    assert not at.exception
    assert at.sidebar.radio[0].options == ["Request queue"]


def test_unknown_user_is_stopped_with_message(app_for: Callable[[str], AppTest]):
    at = app_for("ghost@nowhere.example")
    assert not at.exception
    assert any("not provisioned" in e.value for e in at.error)
    assert not at.sidebar.radio


def test_demo_user_switcher_changes_principal(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    switcher = at.sidebar.selectbox(key="demo_user")
    switcher.select(OPS).run()
    assert at.sidebar.radio[0].options == ["Request queue"]
