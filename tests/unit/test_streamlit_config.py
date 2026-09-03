"""The Streamlit upload cap must equal the attachment policy, or the policy cannot protect memory."""

import tomllib
from pathlib import Path

from retpack_core.attachments import load_attachment_policy


def test_upload_size_matches_policy():
    cfg = tomllib.loads(Path(".streamlit/config.toml").read_text())
    policy = load_attachment_policy(Path("config/attachments.yaml"))
    assert cfg["server"]["maxUploadSize"] == policy.max_size_mb
    assert cfg["client"]["showErrorDetails"] == "none"
