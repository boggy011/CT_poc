"""Render intake widgets from the field specification."""

import math
from collections.abc import Mapping
from typing import Any

import streamlit as st

from retpack_core.fieldspec import FieldSpec, FieldType, FormSpec
from retpack_core.services import Choice

KEY_PREFIX = "f_"


def render_field(f: FieldSpec, choices: Mapping[str, tuple[Choice, ...]], *, key_prefix: str = KEY_PREFIX) -> Any:
    """Render the widget for one field and return its raw value (None when untouched)."""
    label = f"{f.label} *" if f.required else f.label
    key = f"{key_prefix}{f.name}"
    if f.type is FieldType.ENUM:
        options = choices.get(f.name, ())
        labels = {c.value: c.label for c in options}
        return st.selectbox(label, [c.value for c in options], index=None, format_func=lambda v: labels.get(v, v), key=key, help=f.help, placeholder="Select…")
    if f.type is FieldType.STRING:
        return st.text_input(label, key=key, max_chars=f.effective_max_length, help=f.help)
    if f.type is FieldType.TEXT:
        return st.text_area(label, key=key, max_chars=f.effective_max_length, help=f.help)
    if f.type is FieldType.INTEGER:
        lo = math.ceil(f.min) if f.min is not None else None
        hi = math.floor(f.max) if f.max is not None else None
        return st.number_input(label, key=key, value=None, step=1, min_value=lo, max_value=hi, help=f.help)
    if f.type is FieldType.DECIMAL:
        step = 10.0**-f.effective_scale
        lo_f = float(f.min) if f.min is not None else None
        hi_f = float(f.max) if f.max is not None else None
        return st.number_input(label, key=key, value=None, step=step, format=f"%.{f.effective_scale}f", min_value=lo_f, max_value=hi_f, help=f.help)
    return st.date_input(label, key=key, value=None, help=f.help, format="YYYY-MM-DD")


def render_form(spec: FormSpec, choices: Mapping[str, tuple[Choice, ...]], *, skip: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Render every field of ``spec`` grouped by section; return raw values keyed by field name."""
    values: dict[str, Any] = {}
    for section in spec.sections:
        fields = [f for f in spec.fields_in(section.name) if f.name not in skip]
        if not fields:
            continue
        st.subheader(section.label)
        for f in fields:
            values[f.name] = render_field(f, choices)
    return values


def clear_form_state(spec: FormSpec, *, extra_keys: tuple[str, ...] = (), extra_prefixes: tuple[str, ...] = ("att_",)) -> None:
    """Forget widget values so the next render starts blank."""
    for f in spec.fields:
        st.session_state.pop(f"{KEY_PREFIX}{f.name}", None)
    for key in extra_keys:
        st.session_state.pop(key, None)
    for state_key in list(st.session_state):
        if str(state_key).startswith(extra_prefixes):
            st.session_state.pop(state_key, None)
