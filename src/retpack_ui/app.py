"""RetPack Portal entry point: resolve identity, route by role."""

import logging
import uuid
from collections.abc import Callable

import streamlit as st

from retpack_adapters.factory import Container
from retpack_core.errors import RetPackError
from retpack_core.principal import Principal
from retpack_ui.nav import NAV_MY_REQUESTS, NAV_NEW_REQUEST, NAV_QUEUE
from retpack_ui.screens import intake, internal_queue, my_requests
from retpack_ui.state import DEMO_USER_KEY, get_container, real_email, resolve_principal, show_switcher
from retpack_ui.theme import LOGO, LOGO_ICON, LOGO_ON_DARK, eyebrow, inject_css, role_label

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
Page = Callable[[Container, Principal], None]

CUSTOMER_PAGES: dict[str, Page] = {NAV_NEW_REQUEST: intake.render, NAV_MY_REQUESTS: my_requests.render}
INTERNAL_PAGES: dict[str, Page] = {NAV_QUEUE: internal_queue.render}


def _demo_user_switcher(container: Container, real: str | None) -> None:
    emails = list(container.demo_users)
    current = real if container.demo_mode == "impersonate" else container.settings.mock_user
    if current and current not in emails:
        emails.insert(0, current)
    index = emails.index(current) if current in emails else 0
    st.divider()
    with st.expander(":material/science: Demo Mode", expanded=container.demo_mode == "impersonate"):
        if container.demo_mode == "impersonate":
            st.warning(
                "Demo mode: view the portal as a demo customer or team member. Your own sign-in stays verified and every switch is logged.",
                icon=":material/warning:",
            )
        else:
            st.warning("Demo mode: identity is not verified. Pick a user to see the portal as them.", icon=":material/warning:")
        st.selectbox("View as", emails, index=index, key=DEMO_USER_KEY)


def _signed_in_block(principal: Principal) -> None:
    st.divider()
    real = real_email()
    if real and real != principal.email:
        eyebrow("Viewing as")
        st.text(principal.email)
        st.badge(role_label(principal), color="primary" if principal.is_internal else "gray", icon=":material/person:")
        st.caption(f"Signed in as {real}")
    else:
        eyebrow("Signed in as")
        st.text(principal.email)
        st.badge(role_label(principal), color="primary" if principal.is_internal else "gray", icon=":material/person:")


def _not_provisioned() -> None:
    left, _ = st.columns([2, 3])
    with left:
        st.image(str(LOGO), width=320)
        st.error("Your account is not provisioned for the RetPack portal. Contact your ABI representative.", icon=":material/lock:")


def main() -> None:
    """Render the app for the current request."""
    st.set_page_config(page_title="RetPack Portal", page_icon=str(LOGO_ICON), layout="wide", initial_sidebar_state="expanded")
    inject_css()
    st.logo(str(LOGO_ON_DARK), size="large", icon_image=str(LOGO_ICON))
    container = get_container()
    principal = resolve_principal(container)
    real = real_email()
    real_is_internal = bool(real and container.directory is not None and container.directory.is_internal(real))
    switcher = show_switcher(container, real, real_is_internal)
    if principal is None:
        with st.sidebar:
            if switcher:
                _demo_user_switcher(container, real)
        _not_provisioned()
        st.stop()
    pages = INTERNAL_PAGES if principal.is_internal else CUSTOMER_PAGES
    with st.sidebar:
        eyebrow("Menu")
        choice = st.radio("Menu", list(pages), key="nav", label_visibility="collapsed")
        _signed_in_block(principal)
        if switcher:
            _demo_user_switcher(container, real)
        st.divider()
        st.caption("RetPack Portal · ABI International Supply Chain")
    _render_guarded(pages[choice], container, principal)


def _render_guarded(page: Page, container: Container, principal: Principal) -> None:
    """Never let an exception reach the browser with internals attached."""
    try:
        page(container, principal)
    except RetPackError as exc:
        st.error(str(exc))
    except Exception:
        ref = uuid.uuid4().hex[:8]
        logger.exception("unhandled error [%s] for %s", ref, principal.email)
        st.error(f"Something went wrong. Please try again or contact support with reference {ref}.")


main()
