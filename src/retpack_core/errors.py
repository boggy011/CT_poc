"""Domain exceptions raised by the core and its adapters."""

from collections.abc import Mapping


class RetPackError(Exception):
    """Base class for all RetPack domain errors."""


class NotFoundError(RetPackError):
    """The requested object does not exist for this principal.

    Raised for cross-tenant access too, so that existence of another
    tenant's data is never leaked through a distinct error type.
    """


class ConcurrencyConflictError(RetPackError):
    """An append was attempted with a stale expected sequence number."""


class InvalidAttachmentError(RetPackError):
    """Uploaded bytes are not an acceptable PDF attachment."""


class ConfigError(RetPackError):
    """A configuration file (field spec, attachment spec) is invalid."""


class ValidationFailedError(RetPackError):
    """Submitted values violate the field specification.

    Attributes:
        errors: Field name to list of human-readable messages.
    """

    def __init__(self, errors: Mapping[str, list[str]]) -> None:
        self.errors: dict[str, list[str]] = {k: list(v) for k, v in errors.items()}
        summary = "; ".join(f"{k}: {', '.join(v)}" for k, v in self.errors.items())
        super().__init__(f"validation failed: {summary}")


class NotPermittedError(RetPackError):
    """The principal's role does not allow this action."""


class StateError(RetPackError):
    """The action is not valid in the submission's current status."""
