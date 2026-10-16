"""First-party plugins run in the documents process, so they are held to a rule
(RESEARCH §23): no I/O, and no imports beyond ``loft_wire``.

Read from the SOURCE with ``ast`` (as loft-wire's own dependency gate does),
with count floors so a walk that finds nothing cannot pass. Two tiers:

* every module may import ``loft_wire``, ``loft_plugins`` and a short list of
  pure standard-library modules (no ``os``, ``io``, ``pathlib``, ``socket``,
  ``subprocess``, ``importlib`` ...);
* the registry alone may also import ``pydantic`` (to re-validate members) and
  ``time`` (the 2 s cap); a plugin may not.

No module may call ``open``, ``eval``, ``exec``, ``compile``, ``__import__``,
``input`` or ``breakpoint``. And the distribution declares ``loft-wire`` and
nothing else.
"""

import ast
import tomllib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PACKAGE_ROOT / "src" / "loft_plugins"

PURE_STDLIB = frozenset(
    {
        "collections",
        "dataclasses",
        "decimal",
        "enum",
        "fractions",
        "functools",
        "itertools",
        "math",
        "re",
        "typing",
        "uuid",
    }
)
ALLOWED = PURE_STDLIB | {"loft_wire", "loft_plugins"}
#: Modules that run the plugins rather than being one.
FRAMEWORK = {"registry.py": {"pydantic", "time"}}
FORBIDDEN_CALLS = frozenset(
    {"open", "eval", "exec", "compile", "__import__", "input", "breakpoint"}
)
MIN_MODULES = 6
MIN_IMPORTS = 20


def _sources() -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
    ]


def _imports(tree: ast.Module) -> set[str]:
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative imports hide what is imported"
            assert node.module is not None
            seen.add(node.module.split(".")[0])
    return seen


def test_plugins_import_only_loft_wire_and_pure_stdlib() -> None:
    sources = _sources()
    assert len(sources) >= MIN_MODULES, f"walked only {len(sources)} module(s)"
    total = 0
    offences: list[str] = []
    for path, tree in sources:
        imports = _imports(tree)
        total += len(imports)
        allowed = ALLOWED | FRAMEWORK.get(path.name, set())
        offences += [f"{path.name}: imports {name!r}" for name in imports - allowed]
    assert total >= MIN_IMPORTS, f"saw only {total} import(s)"
    assert not offences, "\n".join(offences)


def test_plugins_do_no_io() -> None:
    offences = [
        f"{path.name}:{node.lineno}: calls {node.func.id}()"
        for path, tree in _sources()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in FORBIDDEN_CALLS
    ]
    assert not offences, "\n".join(offences)


def test_the_distribution_depends_on_loft_wire_only() -> None:
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == ["loft-wire"]
    assert project["license"] == "MIT"


def test_the_gate_can_fail() -> None:
    """The walk sees a forbidden import and a forbidden call when one exists."""
    tree = ast.parse("import os\nfrom pathlib import Path\nopen('x')\n")
    assert _imports(tree) - ALLOWED == {"os", "pathlib"}
    calls = [
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert set(calls) & FORBIDDEN_CALLS == {"open"}
