"""Structured audit trail of authorization-relevant events (NFR-01).

One JSON object per line on the ``retpack.audit`` logger. Never includes field
values or document contents; identifiers only.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from retpack_core.principal import Principal

audit_logger = logging.getLogger("retpack.audit")


def audit(event: str, principal: Principal | None = None, **fields: Any) -> None:
    """Emit one audit record.

    Args:
        event: Short snake_case name, e.g. ``submission_created``, ``access_denied``.
        principal: Acting principal, if any.
        **fields: Identifiers to include (submission_id, account_id, field, ...).
    """
    record: dict[str, Any] = {"ts": datetime.now(UTC).isoformat(), "event": event}
    if principal is not None:
        record["actor"] = principal.email
        record["role"] = principal.role.value
    record.update({k: v for k, v in fields.items() if v is not None})
    audit_logger.info(json.dumps(record, default=str, separators=(",", ":")))
