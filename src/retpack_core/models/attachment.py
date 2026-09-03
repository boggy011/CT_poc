"""Attachment metadata.

The portal treats PDF bytes as opaque. Only metadata is modelled so that
cardinality and duplicate rules can be applied as configuration.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AttachmentMeta(BaseModel):
    """Typed metadata row for one stored PDF."""

    model_config = ConfigDict(frozen=True)

    submission_id: str
    account_id: str
    doc_type: str
    seq: int = Field(ge=1)
    original_filename: str = Field(max_length=255, pattern=r'^[^\x00-\x1f\x7f"\\/]+$')
    storage_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    page_count: int = Field(ge=0)
    has_text_layer: bool
    uploaded_at: datetime
    uploaded_by: str
