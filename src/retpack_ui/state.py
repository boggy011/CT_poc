"""Process-wide container and per-request principal resolution for the Streamlit app."""

import os
from collections.abc import Mapping

import streamlit as st

from retpack_adapters.factory import Container, Settings, build_container
from retpack_adapters.identity.mock import MockIdentityProvider
from retpack_core.principal import Principal

_CONTAINER: Container | None = None


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
    """Resolve the signed-in principal on every rerun. Never cached in session state."""
    identity = container.identity
    if isinstance(identity, MockIdentityProvider):
        return identity.resolve(request_headers(), override_email=st.session_state.get("demo_user"))
    return identity.resolve(request_headers())
