"""Apply ``.sql`` migration files through an executor. Deliberately minimal: no versioning table, idempotent DDL."""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from retpack_adapters.sql.executor import SqlExecutor

_PLACEHOLDER = re.compile(r"\$\{([a-z_]+)\}")


def render(sql: str, variables: Mapping[str, str]) -> str:
    """Substitute ``${name}`` placeholders; unknown names are an error."""

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise KeyError(f"migration placeholder ${{{name}}} has no value")
        return variables[name]

    return _PLACEHOLDER.sub(sub, sql)


def split_statements(sql: str) -> list[str]:
    """Split on ``;`` at end of line, dropping comment-only lines and blanks."""
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    statements, current = [], []
    for line in lines:
        current.append(line)
        if line.rstrip().endswith(";"):
            statement = "\n".join(current).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            current = []
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def apply_files(executor: SqlExecutor, files: Iterable[Path], variables: Mapping[str, str]) -> int:
    """Run every statement of every file in order. Returns the number of statements executed."""
    count = 0
    for path in files:
        for statement in split_statements(render(Path(path).read_text(encoding="utf-8"), variables)):
            executor.execute(statement)
            count += 1
    return count


def migration_files(directory: Path) -> list[Path]:
    """``*.sql`` files in lexical order."""
    return sorted(Path(directory).glob("*.sql"))
