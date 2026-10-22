"""Fresh-interpreter tree-export determinism, half B of the tree goldens.

One subprocess rebuild per golden outgrew a pytest shard inside
test_export.py, so the gate is halved across two modules (a shard packs whole
files). The check and the halving live in conftest.py.
"""

from collections.abc import Callable
from pathlib import Path


def test_tree_export_is_byte_deterministic_across_interpreter_restart(
    restart_tree_model: Path,
    assert_tree_export_restart_stable: Callable[[Path], None],
) -> None:
    assert_tree_export_restart_stable(restart_tree_model)
