import pytest

from retpack_core.errors import ConcurrencyConflictError, NotFoundError, RetPackError, ValidationFailedError


def test_errors_share_base():
    assert issubclass(NotFoundError, RetPackError)
    assert issubclass(ConcurrencyConflictError, RetPackError)
    assert issubclass(ValidationFailedError, RetPackError)


def test_validation_failed_carries_field_errors():
    err = ValidationFailedError({"container_no": ["must match ^\\d{10}$"], "qty": ["required"]})
    assert err.errors == {"container_no": ["must match ^\\d{10}$"], "qty": ["required"]}
    assert "container_no" in str(err)
    with pytest.raises(ValidationFailedError):
        raise err


def test_validation_failed_errors_are_immutable_copy():
    source = {"a": ["x"]}
    err = ValidationFailedError(source)
    source["a"].append("y")
    assert err.errors == {"a": ["x"]}
