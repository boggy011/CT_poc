import pytest

from retpack_jobs.maintenance import maintenance_statements, run


class Recorder:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def query(self, sql, params=()):
        return []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        return 0


def test_statements_are_optimize_then_vacuum():
    assert maintenance_statements("c", "s") == ("OPTIMIZE c.s.submission_event", "VACUUM c.s.submission_event RETAIN 720 HOURS")


def test_identifiers_are_checked():
    with pytest.raises(ValueError):
        maintenance_statements("c; DROP", "s")


def test_run_executes_in_order():
    rec = Recorder()
    assert run(rec, "c", "s") == 2
    assert rec.statements[0].startswith("OPTIMIZE") and rec.statements[1].startswith("VACUUM")
