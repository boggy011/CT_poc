"""RetPack Portal entry point: resolve identity, route by role."""

from collections.abc import Callable

import streamlit as st

from retpack_adapters.factory import Container
from retpack_adapters.mock.fixtures import list_user_emails
from retpack_core.principal import Principal
from retpack_ui.pages import intake, internal_queue, my_requests
from retpack_ui.state import get_container, resolve_principal

Page = Callable[[Container, Principal], None]

CUSTOMER_PAGES: dict[str, Page] = {"New request": intake.render, "My requests": my_requests.render}
INTERNAL_PAGES: dict[str, Page] = {"Request queue": internal_queue.render}


def _demo_user_switcher(container: Container) -> None:
    emails = list(list_user_emails(container.settings.mock_data_dir))
    current = container.settings.mock_user
    if current and current not in emails:
        emails.append(current)
    index = emails.index(current) if current in emails else 0
    st.sidebar.selectbox("Demo user (mock backend only)", emails, index=index, key="demo_user")


def main() -> None:
    """Render the app for the current request."""
    st.set_page_config(page_title="RetPack Portal", page_icon="🛢️", layout="wide")
    container = get_container()
    if container.backend == "mock":
        _demo_user_switcher(container)
    principal = resolve_principal(container)
    if principal is None:
        st.error("Your account is not provisioned for the RetPack portal. Contact your ABI representative.")
        st.stop()
    pages = INTERNAL_PAGES if principal.is_internal else CUSTOMER_PAGES
    choice = st.sidebar.radio("Navigate", list(pages), key="nav")
    st.sidebar.caption(f"Signed in as {principal.email} · {principal.role.value.lower()}")
    pages[choice](container, principal)


main()
