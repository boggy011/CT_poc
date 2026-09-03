"""Raw HTML is confined to the theme module, and there it never carries record or user data."""

import re
from pathlib import Path

UI = Path("src/retpack_ui")


def test_unsafe_html_only_in_theme_module():
    offenders = [p for p in UI.rglob("*.py") if "unsafe_allow_html" in p.read_text() and p.name != "theme.py"]
    assert offenders == []


def test_theme_html_escapes_every_interpolation():
    src = (UI / "theme.py").read_text()
    for call in re.findall(r"st\.markdown\((f?)[\'\"](.*?)[\'\"], unsafe_allow_html=True\)", src):
        is_fstring, body = call
        if is_fstring:
            for expr in re.findall(r"\{([^}]+)\}", body):
                assert expr.startswith("html.escape(") or expr in {"sub"}, expr


def test_status_labels_cover_every_status():
    from retpack_core.models import Status
    from retpack_ui.theme import STATUS_COLORS, STATUS_LABELS

    assert set(STATUS_LABELS) == set(Status) == set(STATUS_COLORS)
    assert all(label[0].isupper() for label in STATUS_LABELS.values())
