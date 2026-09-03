"""RetPack Portal entry point: resolve identity, route by role."""

import logging
import uuid
from collections.abc import Callable

import streamlit as st

from retpack_adapters.factory import Container
from retpack_core.errors import RetPackError
from retpack_core.principal import Principal
from retpack_ui.pages import intake, internal_queue, my_requests
from retpack_ui.state import DEMO_USER_KEY, get_container, resolve_principal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
Page = Callable[[Container, Principal], None]

CUSTOMER_PAGES: dict[str, Page] = {"New request": intake.render, "My requests": my_requests.render}
INTERNAL_PAGES: dict[str, Page] = {"Request queue": internal_queue.render}


def _demo_user_switcher(container: Container) -> None:
    emails = list(container.demo_users)
    current = container.settings.mock_user
    if current and current not in emails:
        emails.append(current)
    index = emails.index(current) if current in emails else 0
    st.sidebar.warning("Demo mode: identity is not verified.")
    st.sidebar.selectbox("Demo user (mock backend only)", emails, index=index, key=DEMO_USER_KEY)


def main() -> None:
    """Render the app for the current request."""
    st.set_page_config(page_title="RetPack Portal", page_icon="🛢️", layout="wide")
    container = get_container()
    if container.demo_users:
        _demo_user_switcher(container)
    principal = resolve_principal(container)
    if principal is None:
        st.error("Your account is not provisioned for the RetPack portal. Contact your ABI representative.")
        st.stop()
    pages = INTERNAL_PAGES if principal.is_internal else CUSTOMER_PAGES
    choice = st.sidebar.radio("Navigate", list(pages), key="nav")
    st.sidebar.caption(f"Signed in as {principal.email} · {principal.role.value.lower()}")
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
