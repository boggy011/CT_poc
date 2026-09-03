from collections.abc import Callable

from streamlit.testing.v1 import AppTest

from retpack_core.principal import Principal, Role
from retpack_ui import state
from tests.ui.conftest import ANNA, BRAM
from tests.ui.helpers import go


def test_customer_sees_only_own_requests(app_for: Callable[[str], AppTest]):
    at = go(app_for(ANNA), "My requests")
    assert not at.exception
    table = at.dataframe[0].value
    assert set(table["Account"]) == {"A1", "A2"}
    assert len(table) == 6
    internal = Principal(email="ops1@abi.example", account_ids=frozenset(), role=Role.INTERNAL)
    all_ids = {s.submission_id for s in state.get_container().ports.submissions.list_submissions(internal)}
    bram_ids = {
        s.submission_id
        for s in state.get_container().ports.submissions.list_submissions(Principal(email=BRAM, account_ids=frozenset({"B1"}), role=Role.CUSTOMER))
    }
    rendered = " ".join(str(e.value) for e in list(at.markdown) + list(at.caption)) + table.to_string()
    assert all(sid[-12:].upper() not in rendered for sid in bram_ids)
    assert len(all_ids) == 11


def test_balances_are_plain_numbers(app_for: Callable[[str], AppTest]):
    at = go(app_for(ANNA), "My requests")
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["North Sea Distribution BV (A1)"] == "45"
    assert metrics["North Sea Distribution - Antwerp depot (A2)"] == "2"


def test_status_is_validated_or_not_and_credit_note_shown(app_for: Callable[[str], AppTest]):
    at = go(app_for(ANNA), "My requests")
    table = at.dataframe[0].value
    assert set(table["Status"]) == {"Not validated", "Validated"}
    assert "CN-2026-0451" in set(table["Credit note"])
    with_cn = table[table["Credit note"] == "CN-2026-0451"].iloc[0]["Reference"]
    box = at.selectbox(key="my_selected")
    box.select_index([str(o) for o in box.options].index(with_cn)).run()
    assert any("CN-2026-0451" in i.value for i in at.info)
    assert "RO-7000123" not in " ".join(e.value for e in list(at.success) + list(at.info))


def test_bram_sees_three(app_for: Callable[[str], AppTest]):
    at = go(app_for(BRAM), "My requests")
    assert len(at.dataframe[0].value) == 3
