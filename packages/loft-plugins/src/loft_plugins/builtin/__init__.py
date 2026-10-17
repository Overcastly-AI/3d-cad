"""The first-party plugins Loft ships: reviewed code, run in the documents
process, no I/O and no imports beyond ``loft_wire`` (tests/test_import_lint.py).

Every RELEASED version stays listed here forever: a stored feature pins its
version and is expanded by it, and goldens per version prove old ones
byte-identical (RESEARCH §23).
"""

from loft_plugins.api import Plugin
from loft_plugins.builtin.deck import DECK_V1
from loft_plugins.builtin.twisted_prism import TWISTED_PRISM_V1

BUILTIN_PLUGINS: tuple[Plugin, ...] = (TWISTED_PRISM_V1, DECK_V1)
