"""Time-ordered identifier generation.

Delta has no reliable sequence primitive, so identifiers are generated in
application code. UUIDv7 is time-ordered, which keeps event scans and
Delta file layouts roughly chronological.
"""

import uuid_utils


def new_id() -> str:
    """Return a new UUIDv7 as a canonical 36-character string."""
    return str(uuid_utils.uuid7())
