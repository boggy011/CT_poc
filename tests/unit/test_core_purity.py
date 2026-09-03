"""``retpack_core`` must stay importable with zero Databricks / Streamlit / DB-driver dependencies (req. 5.1)."""

import ast
import json
import subprocess
import sys
from pathlib import Path

FORBIDDEN_ROOTS = {"streamlit", "databricks", "pyspark", "psycopg", "psycopg2", "sqlalchemy", "retpack_adapters", "retpack_ui", "retpack_jobs"}
CORE = Path("src/retpack_core")


def test_no_forbidden_imports_in_core_source():
    offenders = []
    for path in CORE.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in FORBIDDEN_ROOTS:
                    offenders.append(f"{path}: {name}")
    assert offenders == []


def test_importing_core_loads_no_forbidden_modules():
    script = (
        "import sys, json, pkgutil, importlib\n"
        "import retpack_core\n"
        "for m in pkgutil.walk_packages(retpack_core.__path__, 'retpack_core.'):\n"
        "    importlib.import_module(m.name)\n"
        f"forbidden = {sorted(FORBIDDEN_ROOTS)!r}\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in forbidden)))\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True, env={"PYTHONPATH": "src"})
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []
