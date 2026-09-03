"""AppTest fixtures: run the real app against the mock backend with a fresh container per test."""

from collections.abc import Callable
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from retpack_ui import state

APP = str(Path(__file__).resolve().parents[2] / "src" / "retpack_ui" / "app.py")
ANNA = "anna@northsea-distribution.example"
BRAM = "bram@rhine-logistics.example"
OPS = "ops1@abi.example"


@pytest.fixture
def app_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], AppTest]:
    monkeypatch.setenv("RETPACK_SUBMISSION_BACKEND", "mock")
    monkeypatch.setenv("RETPACK_ATTACHMENT_DIR", str(tmp_path / "att"))
    state.reset_container()

    def _make(user: str) -> AppTest:
        monkeypatch.setenv("RETPACK_MOCK_USER", user)
        state.reset_container()
        at = AppTest.from_file(APP, default_timeout=60)
        return at.run()

    return _make
