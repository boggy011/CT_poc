from collections.abc import Callable

from streamlit.testing.v1 import AppTest

from retpack_ui.nav import NAV_MY_REQUESTS, NAV_NEW_REQUEST, NAV_QUEUE
from tests.ui.conftest import ANNA, OPS


def test_customer_sees_two_pages(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    assert not at.exception
    nav = at.sidebar.radio[0]
    assert nav.options == [NAV_NEW_REQUEST, NAV_MY_REQUESTS]
    assert ANNA in " ".join(t.value for t in at.sidebar.text)


def test_internal_sees_one_page(app_for: Callable[[str], AppTest]):
    at = app_for(OPS)
    assert not at.exception
    assert at.sidebar.radio[0].options == [NAV_QUEUE]


def test_unknown_user_is_stopped_with_message(app_for: Callable[[str], AppTest]):
    at = app_for("ghost@nowhere.example")
    assert not at.exception
    assert any("not provisioned" in e.value for e in at.error)
    assert not at.sidebar.radio


def test_demo_user_switcher_changes_principal_and_purges_session(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    at.session_state["intake_result"] = "anna-only"
    at.session_state["queue_seen"] = ("x", 1)
    switcher = at.sidebar.selectbox(key="demo_user")
    switcher.select(OPS).run()
    assert not at.exception
    assert at.sidebar.radio[0].options == [NAV_QUEUE]
    assert "intake_result" not in at.session_state
    assert "queue_seen" not in at.session_state
    assert at.session_state["_principal_email"] == OPS


def test_demo_mode_banner_shown(app_for: Callable[[str], AppTest]):
    at = app_for(ANNA)
    assert any("Demo mode" in w.value for w in at.sidebar.warning)
