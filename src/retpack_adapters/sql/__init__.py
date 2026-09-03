"""Backend-neutral SQL repositories.

The repositories here contain all scoping, concurrency and folding logic once.
A ``Dialect`` supplies the few statements that differ per engine and an
``SqlExecutor`` runs them. The same code is exercised by the contract suite on
SQLite and, env-gated, on Delta and Lakebase.
"""

from retpack_adapters.sql.executor import Dialect, SqlExecutor
from retpack_adapters.sql.reference import ReferenceTables, SqlAccountDirectory, SqlReferenceRepository
from retpack_adapters.sql.submissions import SqlSubmissionRepository

__all__ = ["Dialect", "ReferenceTables", "SqlAccountDirectory", "SqlExecutor", "SqlReferenceRepository", "SqlSubmissionRepository"]
