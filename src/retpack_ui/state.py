"""Process-wide container and per-request principal resolution for the Streamlit app.

Session state may hold principal-scoped objects (a submitted request, the
queue selection). It is bound to the principal that produced it: whenever the
resolved identity changes, every key except the demo switcher is discarded.
"""

import logging
import os
from collections.abc import Mapping

import streamlit as st

from retpack_adapters.factory import Container, Settings, build_container
from retpack_adapters.identity.common import principal_for
from retpack_core.audit import audit
from retpack_core.principal import Principal

logger = logging.getLogger(__name__)
_CONTAINER: Container | None = None

BOUND_EMAIL_KEY = "_principal_email"
REAL_EMAIL_KEY = "_real_email"
DEMO_USER_KEY = "demo_user"
FORWARDED_EMAIL = "X-Forwarded-Email"
_KEEP_ON_IDENTITY_CHANGE = frozenset({DEMO_USER_KEY, BOUND_EMAIL_KEY, REAL_EMAIL_KEY})


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

    Local backends (``demo_mode == "header"``) let the demo switcher supply the
    forwarded-email header the mock provider reads. Workspace backends verify
    the real user from the token and, only in ``impersonate`` mode, let a real
    internal user view the portal as a demo user (see ``effective_principal``).
    """
    headers = dict(request_headers())
    override = _override(container)
    if override and container.demo_mode == "header":
        headers[FORWARDED_EMAIL] = override
    real = container.identity.resolve(headers)
    if real is None:
        forwarded = sorted(k.lower() for k in headers if k.lower().startswith("x-forwarded"))
        logger.info("no principal resolved; forwarded headers present: %s", forwarded)  # names only, never values
    principal = effective_principal(container, real, override)
    bind_session(principal)
    st.session_state[REAL_EMAIL_KEY] = real.email if real else None
    return principal


def _override(container: Container) -> str | None:
    value = st.session_state.get(DEMO_USER_KEY) if container.demo_mode != "off" else None
    return str(value) if value else None


def effective_principal(container: Container, real: Principal | None, override: str | None) -> Principal | None:
    """Apply demo impersonation. Only a verified internal user may view as someone else, and only when enabled."""
    if container.demo_mode != "impersonate" or real is None or not override or override.lower() == real.email:
        return real
    if not real.is_internal or container.directory is None:
        return real
    impersonated = principal_for(container.directory, override)
    if impersonated is None:
        return real
    audit("demo_impersonation", real, viewing_as=impersonated.email, role=impersonated.role.value)
    return impersonated


def show_switcher(container: Container, real: str | None, real_is_internal: bool) -> bool:
    """Local backends always offer the switcher; workspace backends only to a verified internal user."""
    if container.demo_mode == "header":
        return True
    return container.demo_mode == "impersonate" and real is not None and real_is_internal


def real_email() -> str | None:
    """Token-verified email of the signed-in user for this run (None outside a run)."""
    value = st.session_state.get(REAL_EMAIL_KEY)
    return str(value) if value else None


def bind_session(principal: Principal | None) -> None:
    """Purge principal-scoped session state when the identity changes."""
    email = principal.email if principal else None
    if st.session_state.get(BOUND_EMAIL_KEY, None) != email:
        for key in [k for k in st.session_state if k not in _KEEP_ON_IDENTITY_CHANGE]:
            del st.session_state[key]
        st.session_state[BOUND_EMAIL_KEY] = email
