"""Process-wide container and per-request principal resolution for the Streamlit app.

Session state may hold principal-scoped objects (a submitted request, the
queue selection). It is bound to the principal that produced it: whenever the
resolved identity changes, every key except the demo switcher is discarded.
"""

import os
from collections.abc import Mapping

import streamlit as st

from retpack_adapters.factory import Container, Settings, build_container
from retpack_core.principal import Principal

_CONTAINER: Container | None = None

BOUND_EMAIL_KEY = "_principal_email"
DEMO_USER_KEY = "demo_user"
FORWARDED_EMAIL = "X-Forwarded-Email"
_KEEP_ON_IDENTITY_CHANGE = frozenset({DEMO_USER_KEY, BOUND_EMAIL_KEY})


def get_container() -> Container:
    """Build the adapter container once per process."""
    global _CONTAINER
    if _CONTAINER is None:
        _CONTAINER = build_container(Settings.from_env(os.environ))
    return _CONTAINER


def reset_container() -> None:
    """Drop the cached container (tests)."""
    global _CONTAINER
    _CONTAINER = None


def request_headers() -> Mapping[str, str]:
    """Platform headers for this request; empty outside a real server (e.g. AppTest)."""
    try:
        return dict(st.context.headers)
    except Exception:
        return {}


def resolve_principal(container: Container) -> Principal | None:
    """Resolve the signed-in principal on every rerun and bind session state to it.

    With the mock backend the demo switcher overrides the identity by
    supplying the forwarded-email header the mock provider reads; no other
    backend exposes ``demo_users`` so the override path does not exist there.
    """
    headers = dict(request_headers())
    override = st.session_state.get(DEMO_USER_KEY) if container.demo_users else None
    if override:
        headers[FORWARDED_EMAIL] = str(override)
    principal = container.identity.resolve(headers)
    bind_session(principal)
    return principal


def bind_session(principal: Principal | None) -> None:
    """Purge principal-scoped session state when the identity changes."""
    email = principal.email if principal else None
    if st.session_state.get(BOUND_EMAIL_KEY, None) != email:
        for key in [k for k in st.session_state if k not in _KEEP_ON_IDENTITY_CHANGE]:
            del st.session_state[key]
        st.session_state[BOUND_EMAIL_KEY] = email
