"""Fresh-interpreter golden rebuild determinism, half A of the goldens.

The per-golden restart probe was ~80% of test_goldens.py's time and made that
file alone most of a pytest shard (a shard packs whole files), so the gate is
halved across two modules. The check and the halving live in conftest.py.
"""

from collections.abc import Callable
from pathlib import Path


def test_rebuild_is_deterministic_across_interpreter_restart(
    restart_golden_model: Path,
    assert_golden_rebuild_restart_stable: Callable[[Path], None],
) -> None:
    assert_golden_rebuild_restart_stable(restart_golden_model)
