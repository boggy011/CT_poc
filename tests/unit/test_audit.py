import json
import logging

import pytest

from retpack_core.audit import audit
from tests.unit.conftest import CUSTOMER_A


def test_audit_emits_json_line(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger="retpack.audit"):
        audit("submission_created", CUSTOMER_A, submission_id="s1", account_id="A1", skipped=None)
    record = json.loads(caplog.records[-1].getMessage())
    assert record["event"] == "submission_created"
    assert record["actor"] == CUSTOMER_A.email and record["role"] == "CUSTOMER"
    assert record["submission_id"] == "s1" and "skipped" not in record and "ts" in record


def test_services_emit_audit_records(caplog: pytest.LogCaptureFixture, intake, query):
    from io import BytesIO

    from retpack_core.errors import NotFoundError
    from retpack_core.services import UploadedPdf
    from tests.unit.conftest import CUSTOMER_B, VALID_VALUES

    with caplog.at_level(logging.INFO, logger="retpack.audit"):
        result = intake.submit(CUSTOMER_A, VALID_VALUES, [UploadedPdf(doc_type="delivery_note", filename="dn.pdf", stream=BytesIO(b"%PDF-1.7 x"))])
        with pytest.raises(NotFoundError):
            query.get_request(CUSTOMER_B, result.submission.submission_id)
    events = [json.loads(r.getMessage())["event"] for r in caplog.records if r.name == "retpack.audit"]
    assert events == ["submission_created", "access_denied_or_missing"]
    assert all("BL-77" not in r.getMessage() for r in caplog.records)
