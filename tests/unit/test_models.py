from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from retpack_core.models import AttachmentMeta, KegBalance, Sku, Status


def test_status_placeholder_members():
    assert {s.value for s in Status} >= {"SUBMITTED", "VALIDATED", "CPI_PENDING", "CPI_DONE", "CPI_FAILED"}


def _meta(**overrides: object) -> AttachmentMeta:
    base = dict(
        submission_id="0190f0a0-0000-7000-8000-000000000001",
        account_id="A1",
        doc_type="delivery_note",
        seq=1,
        original_filename="dn.pdf",
        storage_path="/tmp/dn.pdf",
        sha256="a" * 64,
        size_bytes=1234,
        page_count=2,
        has_text_layer=True,
        uploaded_at=datetime(2026, 9, 3, tzinfo=UTC),
        uploaded_by="c@dist.com",
    )
    base.update(overrides)
    return AttachmentMeta(**base)  # type: ignore[arg-type]


def test_attachment_meta_is_frozen():
    meta = _meta()
    with pytest.raises(ValidationError):
        meta.seq = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "field,value",
    [
        ("size_bytes", -1),
        ("page_count", -1),
        ("seq", 0),
        ("sha256", "abc"),
        ("original_filename", "../x.pdf"),
        ("original_filename", 'a"b.pdf'),
        ("original_filename", "x" * 256),
    ],
)
def test_attachment_meta_rejects_invalid(field: str, value: object):
    with pytest.raises(ValidationError):
        _meta(**{field: value})


def test_sku_and_balance_models():
    sku = Sku(account_id="A1", sku_code="KEG50", description="50L keg")
    assert sku.sku_code == "KEG50"
    bal = KegBalance(account_id="A1", shipped=120, returned=80, as_of=datetime(2026, 9, 3, tzinfo=UTC))
    assert bal.balance == 40
