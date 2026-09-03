from collections.abc import Callable

from streamlit.testing.v1 import AppTest

from retpack_core import events
from retpack_core.models import Status
from retpack_core.principal import Principal, Role
from retpack_ui import state
from retpack_ui.components.detail import short_ref
from tests.ui.conftest import OPS

INTERNAL = Principal(email=OPS, account_ids=frozenset(), role=Role.INTERNAL)


def open_first(at: AppTest) -> str:
    """Open the first request in the queue and return its full submission id."""
    box = at.selectbox(key="queue_selected")
    box.select_index(0).run()
    return str(at.selectbox(key="queue_selected").value)  # re-fetch after the rerun: value is the raw id


def test_queue_defaults_to_submitted_and_shows_all_when_asked(app_for: Callable[[str], AppTest]):
    at = app_for(OPS)
    assert not at.exception
    table = at.dataframe[0].value
    assert set(table["Status"]) == {"SUBMITTED"} and len(table) == 5
    at.selectbox(key="queue_status").select("All").run()
    assert len(at.dataframe[0].value) == 11


def test_overwrite_records_prior_and_new(app_for: Callable[[str], AppTest]):
    at = app_for(OPS)
    sid = open_first(at)
    before = state.get_container().ports.submissions.get_submission(INTERNAL, sid)
    at.selectbox(key="ow_field").select("quantity").run()
    at.number_input(key="ow_quantity").set_value(before.values["quantity"] + 5)
    at.button(key="overwrite").click().run()
    assert not at.exception
    assert any("updated" in s.value for s in at.success)
    after = state.get_container().ports.submissions.get_submission(INTERNAL, sid)
    assert after.values["quantity"] == before.values["quantity"] + 5
    assert after.original_values["quantity"] == before.values["quantity"]
    assert after.overwrites[-1].actor == OPS
    assert "Changes by the ABI team" in " ".join(m.value for m in at.markdown)


def test_overwrite_with_bad_format_is_rejected(app_for: Callable[[str], AppTest]):
    at = app_for(OPS)
    sid = open_first(at)
    at.selectbox(key="ow_field").select("container_no").run()
    at.text_input(key="ow_container_no").set_value("nope")
    at.button(key="overwrite").click().run()
    assert any("must match" in e.value for e in at.error)
    assert state.get_container().ports.submissions.get_submission(INTERNAL, sid).seq == 1


def test_validate_moves_request_out_of_submitted(app_for: Callable[[str], AppTest]):
    at = app_for(OPS)
    sid = open_first(at)
    at.button(key="validate").click().run()
    assert not at.exception
    assert any("validated" in s.value.lower() for s in at.success)
    sub = state.get_container().ports.submissions.get_submission(INTERNAL, sid)
    assert sub.status is Status.VALIDATED and sub.validated_by == OPS
    assert short_ref(sid) not in [str(o) for o in at.selectbox(key="queue_selected").options]


def test_stale_version_shows_conflict(app_for: Callable[[str], AppTest]):
    at = app_for(OPS)
    sid = open_first(at)
    repo = state.get_container().ports.submissions
    sub = repo.get_submission(INTERNAL, sid)
    other = Principal(email="ops2@abi.example", account_ids=frozenset(), role=Role.INTERNAL)
    repo.append_event(
        other, sid, sub.seq, events.field_overwritten(sid, sub.account_id, actor=other.email, seq=sub.seq + 1, field="seal_no", prior=None, new="X")
    )
    at.button(key="validate").click().run()
    assert any("changed by someone else" in w.value for w in at.warning)
    assert repo.get_submission(INTERNAL, sid).status is Status.SUBMITTED
    # The latest version is now on screen; acting again succeeds.
    at.button(key="validate").click().run()
    assert repo.get_submission(INTERNAL, sid).status is Status.VALIDATED


def test_validated_request_has_no_actions_and_shows_cpi_outcome(app_for: Callable[[str], AppTest]):
    at = app_for(OPS)
    at.selectbox(key="queue_status").select("CPI_FAILED").run()
    open_first(at)
    assert [b for b in at.button if b.key == "validate"] == []
    assert any("unknown sold-to" in e.value for e in at.error)
