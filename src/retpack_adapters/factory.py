"""Build the adapter set for the configured backend.

``RETPACK_SUBMISSION_BACKEND=mock|sqlite|delta|lakebase`` selects the
transactional store. Reference data comes from Delta for the two workspace
backends and from local fixtures otherwise; attachments go to a Unity Catalog
Volume for the workspace backends and to a local directory otherwise.
Databricks libraries are imported lazily so local backends need none of them.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from retpack_adapters.attachments.local import LocalAttachmentStore
from retpack_adapters.identity.mock import MockIdentityProvider
from retpack_adapters.mock.fixtures import list_user_emails, load_directory, load_reference
from retpack_adapters.mock.seed import seed_demo
from retpack_adapters.mock.submissions import InMemorySubmissionRepository
from retpack_adapters.sql import ReferenceTables, SqlAccountDirectory, SqlReferenceRepository, SqlSubmissionRepository
from retpack_adapters.sql.executor import SqlExecutor, delta_dialect, lakebase_dialect, sqlite_dialect
from retpack_adapters.sql.migrate import apply_files, migration_files
from retpack_core.attachments import AttachmentPolicy, load_attachment_policy
from retpack_core.errors import ConfigError
from retpack_core.fieldspec import FormSpec, load_form_spec
from retpack_core.ports import AttachmentStore, IdentityProvider, Ports, ReferenceRepository
from retpack_core.principal import Principal, Role

BACKENDS = ("mock", "sqlite", "delta", "lakebase")
WORKSPACE_BACKENDS = ("delta", "lakebase")
_TRUE = {"1", "true", "yes", "on"}
_SYSTEM = Principal(email="factory@system.local", account_ids=frozenset(), role=Role.SYSTEM)


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    return env.get(name, "1" if default else "0").strip().lower() in _TRUE


@dataclass(frozen=True)
class Settings:
    """Environment-derived configuration."""

    backend: str = "mock"
    field_spec_path: Path = Path("config/fields/placeholder.yaml")
    attachment_policy_path: Path = Path("config/attachments.yaml")
    mock_data_dir: Path = Path("config/mock")
    attachment_dir: Path = Path(".retpack_attachments")
    mock_user: str | None = None
    seed_demo: bool = False
    sqlite_path: Path = Path(".retpack/retpack.db")
    catalog: str = ""
    schema: str = "retpack"
    ref_schema: str = ""
    volume: str = "attachments"
    warehouse_id: str = ""
    lakebase_instance: str = ""
    lakebase_database: str = "databricks_postgres"
    trust_forwarded_email: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        """Read settings from environment variables, applying defaults.

        Raises:
            ConfigError: If the backend name is unknown.
        """
        backend = env.get("RETPACK_SUBMISSION_BACKEND", "mock").strip().lower()
        if backend not in BACKENDS:
            raise ConfigError(f"unknown backend {backend!r}; expected one of {BACKENDS}")
        schema = env.get("RETPACK_SCHEMA", cls.schema)
        return cls(
            backend=backend,
            field_spec_path=Path(env.get("RETPACK_FIELD_SPEC", str(cls.field_spec_path))),
            attachment_policy_path=Path(env.get("RETPACK_ATTACHMENT_POLICY", str(cls.attachment_policy_path))),
            mock_data_dir=Path(env.get("RETPACK_MOCK_DATA_DIR", str(cls.mock_data_dir))),
            attachment_dir=Path(env.get("RETPACK_ATTACHMENT_DIR", str(cls.attachment_dir))),
            mock_user=env.get("RETPACK_MOCK_USER") or None,
            seed_demo=_flag(env, "RETPACK_MOCK_SEED", False),
            sqlite_path=Path(env.get("RETPACK_SQLITE_PATH", str(cls.sqlite_path))),
            catalog=env.get("RETPACK_CATALOG", ""),
            schema=schema,
            ref_schema=env.get("RETPACK_REF_SCHEMA", schema),
            volume=env.get("RETPACK_VOLUME", cls.volume),
            warehouse_id=env.get("DATABRICKS_WAREHOUSE_ID", ""),
            lakebase_instance=env.get("RETPACK_LAKEBASE_INSTANCE", ""),
            lakebase_database=env.get("RETPACK_LAKEBASE_DATABASE", cls.lakebase_database),
            trust_forwarded_email=_flag(env, "RETPACK_TRUST_FORWARDED_EMAIL", False),
            extra={k: v for k, v in env.items() if k.startswith("DATABRICKS_")},
        )

    def require(self, *names: str) -> None:
        """Fail fast when a workspace backend is missing configuration.

        Raises:
            ConfigError: Listing every missing setting.
        """
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise ConfigError(f"backend {self.backend!r} needs settings: {', '.join(missing)}")

    @property
    def volume_root(self) -> str:
        """Volume path prefix for attachments."""
        return f"/Volumes/{self.catalog}/{self.schema}/{self.volume}"


@dataclass(frozen=True)
class Container:
    """Everything the UI needs, built once per process."""

    backend: str
    settings: Settings
    ports: Ports
    identity: IdentityProvider
    spec: FormSpec
    policy: AttachmentPolicy
    demo_users: tuple[str, ...] = ()
    """Selectable identities for the demo switcher. Empty for every non-mock backend."""


def build_container(settings: Settings, *, executors: Mapping[str, Callable[[], SqlExecutor]] | None = None, files_client: Any = None) -> Container:
    """Construct adapters for ``settings.backend``.

    Args:
        settings: Configuration.
        executors: Optional overrides keyed ``"delta"`` / ``"lakebase"`` (tests).
        files_client: Optional ``FilesClient`` override (tests).

    Raises:
        ConfigError: If configuration files are invalid or workspace settings are missing.
    """
    spec = load_form_spec(settings.field_spec_path)
    policy = load_attachment_policy(settings.attachment_policy_path)
    if settings.backend == "mock":
        return _mock(settings, spec, policy)
    if settings.backend == "sqlite":
        return _sqlite(settings, spec, policy)
    return _workspace(settings, spec, policy, executors or {}, files_client)


def _mock(settings: Settings, spec: FormSpec, policy: AttachmentPolicy) -> Container:
    store = LocalAttachmentStore(settings.attachment_dir, policy=policy)
    repo = InMemorySubmissionRepository()
    if settings.seed_demo:
        seed_demo(repo, store, settings.mock_data_dir)
    ports = Ports(submissions=repo, reference=load_reference(settings.mock_data_dir), attachments=store)
    identity = MockIdentityProvider(load_directory(settings.mock_data_dir), default_email=settings.mock_user)
    return Container("mock", settings, ports, identity, spec, policy, demo_users=list_user_emails(settings.mock_data_dir))


def _sqlite(settings: Settings, spec: FormSpec, policy: AttachmentPolicy) -> Container:
    """Persistent local backend: same SQL repositories as the workspace backends, local files and demo identity."""
    from retpack_adapters.sqlite.executor import SqliteExecutor
    from retpack_adapters.sqlite.seed import seed_reference_tables

    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    db = SqliteExecutor(settings.sqlite_path)
    apply_files(db, migration_files(Path("migrations/sqlite")), {})
    seed_reference_tables(db, settings.mock_data_dir)
    store = LocalAttachmentStore(settings.attachment_dir, policy=policy)
    repo = SqlSubmissionRepository(db, sqlite_dialect())
    if settings.seed_demo and not repo.list_submissions(_SYSTEM, limit=1):
        seed_demo(repo, store, settings.mock_data_dir)
    ports = Ports(submissions=repo, reference=SqlReferenceRepository(db), attachments=store)
    identity = MockIdentityProvider(SqlAccountDirectory(db), default_email=settings.mock_user)
    return Container("sqlite", settings, ports, identity, spec, policy, demo_users=list_user_emails(settings.mock_data_dir))


def _workspace(
    settings: Settings, spec: FormSpec, policy: AttachmentPolicy, executors: Mapping[str, Callable[[], SqlExecutor]], files_client: Any
) -> Container:
    settings.require("catalog", "schema", "warehouse_id")
    delta = executors["delta"]() if "delta" in executors else _delta_executor(settings)
    tables = ReferenceTables.in_schema(f"{settings.catalog}.{settings.ref_schema}")
    reference: ReferenceRepository = SqlReferenceRepository(delta, tables)
    directory = SqlAccountDirectory(delta, tables)
    if settings.backend == "delta":
        submissions = SqlSubmissionRepository(delta, delta_dialect(settings.catalog, settings.schema))
    else:
        settings.require("lakebase_instance")
        lakebase = executors["lakebase"]() if "lakebase" in executors else _lakebase_executor(settings)
        submissions = SqlSubmissionRepository(lakebase, lakebase_dialect(settings.schema))
    attachments: AttachmentStore = _volume_store(settings, policy, files_client)
    identity = _apps_identity(settings, directory)
    return Container(settings.backend, settings, Ports(submissions=submissions, reference=reference, attachments=attachments), identity, spec, policy)


def _delta_executor(settings: Settings) -> SqlExecutor:
    from databricks import sql as dbsql
    from databricks.sdk.core import Config

    from retpack_adapters.delta.executor import DeltaExecutor

    cfg = Config()

    def connect() -> Any:
        return dbsql.connect(
            server_hostname=cfg.hostname, http_path=f"/sql/1.0/warehouses/{settings.warehouse_id}", credentials_provider=lambda: cfg.authenticate
        )

    return DeltaExecutor(connect)


def _lakebase_executor(settings: Settings) -> SqlExecutor:
    import psycopg
    from databricks.sdk import WorkspaceClient

    from retpack_adapters.lakebase.executor import LakebaseExecutor

    w = WorkspaceClient()

    def connect() -> Any:
        instance = w.database.get_database_instance(settings.lakebase_instance)
        credential = w.database.generate_database_credential(instance_names=[settings.lakebase_instance])
        user = w.current_user.me().user_name
        return psycopg.connect(
            host=instance.read_write_dns, dbname=settings.lakebase_database, user=user, password=credential.token, sslmode="require", autocommit=True
        )

    return LakebaseExecutor(connect)


def _volume_store(settings: Settings, policy: AttachmentPolicy, files_client: Any) -> AttachmentStore:
    from retpack_adapters.attachments.volume import VolumeAttachmentStore

    if files_client is None:
        from databricks.sdk import WorkspaceClient

        from retpack_adapters.attachments.sdk_files import SdkFilesClient

        files_client = SdkFilesClient(WorkspaceClient())
    return VolumeAttachmentStore(files_client, root=settings.volume_root, policy=policy)


def _apps_identity(settings: Settings, directory: SqlAccountDirectory) -> IdentityProvider:
    from retpack_adapters.identity.databricks_apps import DatabricksAppsIdentityProvider, SdkTokenIdentityLookup

    host = settings.extra.get("DATABRICKS_HOST", os.environ.get("DATABRICKS_HOST", ""))
    return DatabricksAppsIdentityProvider(directory, SdkTokenIdentityLookup(host), trust_forwarded_email=settings.trust_forwarded_email)
