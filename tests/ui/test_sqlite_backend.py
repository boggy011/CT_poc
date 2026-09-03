"""The persistent local backend must drive the real screens through the shared SQL repositories."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from retpack_ui import state
from tests.ui.conftest import APP, OPS
from tests.ui.helpers import SUBMIT_KEY, fill_valid_form, select_starting_with


@pytest.fixture
def sqlite_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RETPACK_SUBMISSION_BACKEND", "sqlite")
    monkeypatch.setenv("RETPACK_SQLITE_PATH", str(tmp_path / "retpack.db"))
    monkeypatch.setenv("RETPACK_ATTACHMENT_DIR", str(tmp_path / "att"))
    monkeypatch.setenv("RETPACK_MOCK_SEED", "1")

    def _make(user: str) -> AppTest:
        monkeypatch.setenv("RETPACK_MOCK_USER", user)
        state.reset_container()
        return AppTest.from_file(APP, default_timeout=60).run()

    return _make


def test_queue_and_submit_on_sqlite(sqlite_app):
    at = sqlite_app(OPS)
    assert not at.exception
    at.selectbox(key="queue_status").select("All").run()
    assert len(at.dataframe[0].value) == 11

    at = sqlite_app("anna@northsea-distribution.example")
    select_starting_with(at, "account_id", "A1")
    at.run()
    fill_valid_form(at)
    at.button(key=SUBMIT_KEY).click().run()
    assert not at.exception and at.success

    at = sqlite_app(OPS)  # new container, same database file: the request persisted
    assert len(at.dataframe[0].value) == 6
