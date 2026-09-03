"""PDF upload widgets driven by the attachment policy."""

import streamlit as st

from retpack_core.attachments import AttachmentPolicy
from retpack_core.services import UploadedPdf


def render_uploaders(policy: AttachmentPolicy) -> list[UploadedPdf]:
    """One uploader per document type; returns the files chosen so far."""
    uploads: list[UploadedPdf] = []
    cols = st.columns(len(policy.doc_types) or 1)
    for col, d in zip(cols, policy.doc_types, strict=False):
        label = f"{d.label} *" if d.required else d.label
        if d.max_count > 1:
            label = f"{label} (up to {d.max_count})"
        with col:
            chosen = st.file_uploader(label, type=["pdf"], accept_multiple_files=d.max_count > 1, key=f"att_{d.name}")
        if chosen is None:
            continue
        for f in chosen if isinstance(chosen, list) else [chosen]:
            f.seek(0)
            uploads.append(UploadedPdf(doc_type=d.name, filename=f.name, stream=f))
    return uploads
