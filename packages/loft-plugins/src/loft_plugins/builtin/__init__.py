"""The first-party plugins Loft ships: reviewed code, run in the documents
process, no I/O and no imports beyond ``loft_wire`` (tests/test_import_lint.py).

Every RELEASED version stays listed here forever: a stored feature pins its
version and is expanded by it, and goldens per version prove old ones
byte-identical (RESEARCH §23).
"""

from loft_plugins.api import Plugin
from loft_plugins.builtin.building_outline import (
    FLOOR_V1_2,
    FLOOR_V1_3,
    WALL_V1_3,
)
from loft_plugins.builtin.cabinets import CABINETS_V1
from loft_plugins.builtin.crawl_space import FOUNDATION_V1
from loft_plugins.builtin.deck import DECK_V1, DECK_V1_1
from loft_plugins.builtin.floor import FLOOR_V1
from loft_plugins.builtin.interior_wall import INTERIOR_WALL_V1, WALL_V1_4
from loft_plugins.builtin.openings import (
    DOOR_V1,
    DOOR_V1_1,
    DOOR_V1_2,
    DOOR_V1_3,
    DOOR_V1_4,
    WINDOW_V1,
    WINDOW_V1_1,
    WINDOW_V1_2,
    WINDOW_V1_3,
    WINDOW_V1_4,
)
from loft_plugins.builtin.roof import ROOF_V1, ROOF_V1_1
from loft_plugins.builtin.roof_outline import ROOF_V1_4, ROOF_V1_5
from loft_plugins.builtin.roof_valley import ROOF_V1_2, ROOF_V1_3
from loft_plugins.builtin.sheathing import FLOOR_V1_1, WALL_V1_2
from loft_plugins.builtin.slab import SLAB_V1
from loft_plugins.builtin.timber_frame import TIMBER_FRAME_V1
from loft_plugins.builtin.twisted_prism import TWISTED_PRISM_V1
from loft_plugins.builtin.wall import WALL_V1, WALL_V1_1

BUILTIN_PLUGINS: tuple[Plugin, ...] = (
    TWISTED_PRISM_V1,
    DECK_V1,
    DECK_V1_1,
    WALL_V1,
    WALL_V1_1,
    WINDOW_V1,
    DOOR_V1,
    ROOF_V1,
    ROOF_V1_1,
    ROOF_V1_2,
    FLOOR_V1,
    TIMBER_FRAME_V1,
    ROOF_V1_3,
    WALL_V1_2,
    FLOOR_V1_1,
    WALL_V1_3,
    FLOOR_V1_2,
    WINDOW_V1_1,
    DOOR_V1_1,
    ROOF_V1_4,
    WINDOW_V1_2,
    DOOR_V1_2,
    ROOF_V1_5,
    WINDOW_V1_3,
    WINDOW_V1_4,
    DOOR_V1_3,
    FLOOR_V1_3,
    DOOR_V1_4,
    SLAB_V1,
    WALL_V1_4,
    INTERIOR_WALL_V1,
    CABINETS_V1,
    FOUNDATION_V1,
)
