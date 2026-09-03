from pathlib import Path

import pytest

from retpack_core.attachments import AttachmentPolicy, load_attachment_policy, parse_attachment_policy
from retpack_core.errors import ConfigError

PLACEHOLDER = Path("config/attachments.yaml")


def test_placeholder_policy_loads():
    policy = load_attachment_policy(PLACEHOLDER)
    assert policy.max_size_bytes == 25 * 1024 * 1024
    assert policy.doc_type("delivery_note").max_count == 1
    assert policy.doc_type("delivery_note").required is False


def test_unknown_doc_type_is_key_error():
    policy = load_attachment_policy(PLACEHOLDER)
    with pytest.raises(KeyError):
        policy.doc_type("selfie")


def test_check_counts_missing_required_and_too_many():
    policy = parse_attachment_policy(
        {
            "version": 1,
            "max_size_mb": 1,
            "doc_types": [{"name": "dn", "label": "DN", "required": True, "max_count": 1}, {"name": "other", "label": "Other", "max_count": 2}],
        }
    )
    assert policy.check_counts({}) == {"dn": "at least one dn is required"}
    assert policy.check_counts({"dn": 2}) == {"dn": "at most 1 dn allowed"}
    assert policy.check_counts({"dn": 1, "other": 2}) == {}
    assert policy.check_counts({"dn": 1, "weird": 1}) == {"weird": "unknown document type"}


def test_invalid_policy_is_config_error():
    with pytest.raises(ConfigError):
        parse_attachment_policy({"version": 1, "max_size_mb": 1, "doc_types": [{"name": "dn"}]})
    with pytest.raises(ConfigError, match="duplicate"):
        parse_attachment_policy({"version": 1, "max_size_mb": 1, "doc_types": [{"name": "dn", "label": "a"}, {"name": "dn", "label": "b"}]})
    with pytest.raises(ConfigError):
        load_attachment_policy(Path("nope.yaml"))
    assert isinstance(parse_attachment_policy({"version": 1, "max_size_mb": 1, "doc_types": [{"name": "dn", "label": "a"}]}), AttachmentPolicy)
