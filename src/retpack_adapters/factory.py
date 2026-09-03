"""Build the adapter set for the configured backend.

``RETPACK_SUBMISSION_BACKEND=mock|delta|lakebase`` selects the transactional
store. Only the mock backend is wired in Phase A.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from retpack_adapters.attachments.local import LocalAttachmentStore
from retpack_adapters.identity.mock import MockIdentityProvider
from retpack_adapters.mock.fixtures import load_directory, load_reference
from retpack_adapters.mock.seed import seed_demo
from retpack_adapters.mock.submissions import InMemorySubmissionRepository
from retpack_core.attachments import AttachmentPolicy, load_attachment_policy
from retpack_core.errors import ConfigError
from retpack_core.fieldspec import FormSpec, load_form_spec
from retpack_core.ports import IdentityProvider, Ports

BACKENDS = ("mock", "delta", "lakebase")
_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Environment-derived configuration."""

    backend: str = "mock"
    field_spec_path: Path = Path("config/fields/placeholder.yaml")
    attachment_policy_path: Path = Path("config/attachments.yaml")
    mock_data_dir: Path = Path("config/mock")
    attachment_dir: Path = Path(".retpack_attachments")
    mock_user: str | None = None
    seed_demo: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        """Read settings from environment variables, applying defaults.

        Raises:
            ConfigError: If the backend name is unknown.
        """
        backend = env.get("RETPACK_SUBMISSION_BACKEND", "mock").strip().lower()
        if backend not in BACKENDS:
            raise ConfigError(f"unknown backend {backend!r}; expected one of {BACKENDS}")
        return cls(
            backend=backend,
            field_spec_path=Path(env.get("RETPACK_FIELD_SPEC", str(cls.field_spec_path))),
            attachment_policy_path=Path(env.get("RETPACK_ATTACHMENT_POLICY", str(cls.attachment_policy_path))),
            mock_data_dir=Path(env.get("RETPACK_MOCK_DATA_DIR", str(cls.mock_data_dir))),
            attachment_dir=Path(env.get("RETPACK_ATTACHMENT_DIR", str(cls.attachment_dir))),
            mock_user=env.get("RETPACK_MOCK_USER") or None,
            seed_demo=env.get("RETPACK_MOCK_SEED", "1").strip().lower() in _TRUE,
        )


@dataclass(frozen=True)
class Container:
    """Everything the UI needs, built once per process."""

    backend: str
    settings: Settings
    ports: Ports
    identity: IdentityProvider
    spec: FormSpec
    policy: AttachmentPolicy


def build_container(settings: Settings) -> Container:
    """Construct adapters for ``settings.backend``.

    Raises:
        NotImplementedError: For backends not yet wired (delta, lakebase: Phase B).
        ConfigError: If configuration files are invalid.
    """
    spec = load_form_spec(settings.field_spec_path)
    policy = load_attachment_policy(settings.attachment_policy_path)
    if settings.backend != "mock":
        raise NotImplementedError(f"backend {settings.backend!r} is wired in Phase B")
    store = LocalAttachmentStore(settings.attachment_dir, max_bytes=policy.max_size_bytes)
    repo = InMemorySubmissionRepository()
    if settings.seed_demo:
        seed_demo(repo, store, settings.mock_data_dir)
    ports = Ports(submissions=repo, reference=load_reference(settings.mock_data_dir), attachments=store)
    identity = MockIdentityProvider(load_directory(settings.mock_data_dir), default_email=settings.mock_user)
    return Container(backend="mock", settings=settings, ports=ports, identity=identity, spec=spec, policy=policy)
