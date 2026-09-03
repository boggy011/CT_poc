"""FR-02 structural gate: no repository method can be expressed without a Principal.

Parses the port modules with ``ast`` so the rule holds for every implementation
that satisfies the Protocol, regardless of backend.
"""

import ast
from pathlib import Path

import pytest

PORTS_DIR = Path("src/retpack_core/ports")

# Ports that produce a Principal cannot take one. Everything else must.
EXEMPT_CLASSES = {"IdentityProvider", "AccountDirectory"}


def _port_methods() -> list[tuple[str, str, ast.FunctionDef]]:
    found = []
    for path in sorted(PORTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name in EXEMPT_CLASSES:
                continue
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    found.append((path.name, node.name, item))
    return found


def test_ports_directory_has_ports():
    assert len(_port_methods()) >= 8


@pytest.mark.parametrize("module,cls,func", [(m, c, f) for m, c, f in _port_methods()], ids=lambda x: x if isinstance(x, str) else x.name)
def test_every_port_method_takes_principal_first(module: str, cls: str, func: ast.FunctionDef):
    args = func.args.args
    assert len(args) >= 2, f"{module}:{cls}.{func.name} has no parameter after self"
    assert args[0].arg == "self"
    principal = args[1]
    assert principal.arg == "principal", f"{module}:{cls}.{func.name} first parameter must be 'principal'"
    assert isinstance(principal.annotation, ast.Name) and principal.annotation.id == "Principal", (
        f"{module}:{cls}.{func.name} principal must be annotated Principal"
    )
    assert not func.args.defaults or len(func.args.defaults) < len(args) - 1, f"{module}:{cls}.{func.name} principal must not have a default"
