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
from retpack_ui.state import DEMO_USER_KEY, get_container, resolve_principal
from retpack_ui.theme import LOGO, LOGO_ICON, LOGO_ON_DARK, eyebrow, inject_css, role_label

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
Page = Callable[[Container, Principal], None]

CUSTOMER_PAGES: dict[str, Page] = {NAV_NEW_REQUEST: intake.render, NAV_MY_REQUESTS: my_requests.render}
INTERNAL_PAGES: dict[str, Page] = {NAV_QUEUE: internal_queue.render}


def _demo_user_switcher(container: Container) -> None:
    emails = list(container.demo_users)
    current = container.settings.mock_user
    if current and current not in emails:
        emails.append(current)
    index = emails.index(current) if current in emails else 0
    st.divider()
    with st.expander(":material/science: Demo Mode", expanded=False):
        st.warning("Demo mode: identity is not verified. Pick a user to see the portal as them.", icon=":material/warning:")
        st.selectbox("Demo user", emails, index=index, key=DEMO_USER_KEY)


def _signed_in_block(principal: Principal) -> None:
    st.divider()
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
    if principal is None:
        with st.sidebar:
            if container.demo_users:
                _demo_user_switcher(container)
        _not_provisioned()
        st.stop()
    pages = INTERNAL_PAGES if principal.is_internal else CUSTOMER_PAGES
    with st.sidebar:
        eyebrow("Menu")
        choice = st.radio("Menu", list(pages), key="nav", label_visibility="collapsed")
        _signed_in_block(principal)
        if container.demo_users:
            _demo_user_switcher(container)
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
