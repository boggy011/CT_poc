"""Visual identity helpers.

All HTML here is static, authored in this file, and never interpolates user
or record data: ``unsafe_allow_html`` is used only for the CSS block and for
page headers whose text is a literal from our own page modules (escaped
anyway). A unit test pins that this is the only module using it.
"""

import html
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import streamlit as st

from retpack_core.models import Status
from retpack_core.principal import Principal

ASSETS = Path(__file__).resolve().parents[2] / "assets"
LOGO = ASSETS / "logo.png"
LOGO_ON_DARK = ASSETS / "logo_on_dark.png"
LOGO_ICON = ASSETS / "logo_icon.png"

STATUS_LABELS: dict[Status, str] = {
    Status.SUBMITTED: "Submitted",
    Status.VALIDATED: "Validated",
    Status.CPI_PENDING: "Sending to SAP",
    Status.CPI_DONE: "SAP order created",
    Status.CPI_FAILED: "Needs attention",
}
BadgeColor = Literal["red", "orange", "yellow", "blue", "green", "violet", "gray", "primary"]
STATUS_COLORS: dict[Status, BadgeColor] = {
    Status.SUBMITTED: "blue",
    Status.VALIDATED: "green",
    Status.CPI_PENDING: "orange",
    Status.CPI_DONE: "green",
    Status.CPI_FAILED: "red",
}
CUSTOMER_STATUS_LABELS: dict[bool, str] = {False: "Not validated", True: "Validated"}

_CSS = """
<style>
/* ---- sidebar: radio group styled as a menu ---- */
[data-testid="stSidebar"] [role="radiogroup"] { gap: 2px; }
[data-testid="stSidebar"] [role="radiogroup"] > label {
  padding: 9px 12px; border-radius: 6px; margin: 0; cursor: pointer; width: 100%;
  transition: background .12s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] > label:hover { background: rgba(255,255,255,.06); }
[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
  background: rgba(255,255,255,.10); box-shadow: inset 3px 0 0 #D9905A;
}
[data-testid="stSidebar"] [role="radiogroup"] > label > div:first-child { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] > label p { font-size: 15px; font-weight: 600; }
[data-testid="stSidebar"] hr { margin: 14px 0; opacity: .5; }
[data-testid="stSidebar"] [data-testid="stImage"] img { max-height: 44px; }
[data-testid="stSidebarHeader"] img, [data-testid="stLogo"] { max-width: 200px; height: auto; }
[data-testid="stSidebarLogo"] { background: #FFFFFF; padding: 8px 12px; border-radius: 6px; box-sizing: content-box; }
[data-testid="stSidebar"] > div { overflow-x: hidden; }

/* ---- main area ---- */
[data-testid="stMainBlockContainer"] { padding-top: 2.5rem; }

/* ---- eyebrow labels ---- */
.rp-eyebrow { font-family: "IBM Plex Mono", monospace; font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  opacity: .65; margin: 6px 0 6px; }

/* ---- page header ---- */
.rp-header { padding: 4px 0 14px; border-bottom: 2px solid #1E2530; margin-bottom: 18px; }
.rp-header h1 { margin: 0; font-family: "Barlow Semi Condensed", sans-serif; font-weight: 700; font-size: 34px; line-height: 1.1; }
.rp-header p { margin: 6px 0 0; color: #5B6675; font-size: 15px; max-width: 70ch; }

/* ---- section titles inside bordered containers ---- */
.rp-section { font-family: "Barlow Semi Condensed", sans-serif; font-weight: 600; font-size: 19px; margin: 0 0 4px; }
.rp-section-note { color: #5B6675; font-size: 14px; margin: 0 0 8px; }

/* ---- metric tiles ---- */
[data-testid="stMetric"] { padding: 4px 0; }
[data-testid="stMetricLabel"] p { font-family: "IBM Plex Mono", monospace; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #5B6675; }
[data-testid="stMetricValue"] { font-family: "Barlow Semi Condensed", sans-serif; font-weight: 700; }

/* ---- forms and tables ---- */
[data-testid="stForm"] { border: 0; padding: 0; }
[data-testid="stDataFrame"] { border-radius: 6px; }
div[data-testid="stExpander"] details { border-radius: 6px; }
</style>
"""


def inject_css() -> None:
    """Add the static stylesheet once per run."""
    st.markdown(_CSS, unsafe_allow_html=True)  # static CSS only; see module docstring


def page_header(title: str, subtitle: str | None = None) -> None:
    """Title block with the copper-ruled divider. Arguments are literals from page modules."""
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    st.markdown(f'<div class="rp-header"><h1>{html.escape(title)}</h1>{sub}</div>', unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    """Small uppercase label."""
    st.markdown(f'<div class="rp-eyebrow">{html.escape(text)}</div>', unsafe_allow_html=True)


@contextmanager
def section(title: str, note: str | None = None) -> Iterator[None]:
    """A bordered card with a section title; body rendered by the caller."""
    with st.container(border=True):
        st.markdown(f'<div class="rp-section">{html.escape(title)}</div>', unsafe_allow_html=True)
        if note:
            st.markdown(f'<div class="rp-section-note">{html.escape(note)}</div>', unsafe_allow_html=True)
        yield


def status_badge(status: Status) -> None:
    """Coloured pill for an internal status."""
    st.badge(STATUS_LABELS[status], color=STATUS_COLORS[status])


def customer_status_badge(status: Status) -> None:
    """Coloured pill for the customer-facing status."""
    validated = status is not Status.SUBMITTED
    st.badge(CUSTOMER_STATUS_LABELS[validated], color="green" if validated else "blue")


def role_label(principal: Principal) -> str:
    """Human role name."""
    return "ABI team" if principal.is_internal else "Customer"
