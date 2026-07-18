"""Document display-unit vocabulary — the single home of the length-unit enum.

docs/design/units.md §"the one load-bearing rule": storage and the kernel are
canonical millimetres, forever. A document's ``length_unit`` is DISPLAY metadata
about how to render/parse its canonical mm values — nothing downstream of the
input cell converts. The enum is declared ONCE here and reused by every document
schema (parts, assemblies) so the literal never drifts per document; ``just gen``
exports it and the ts-client imports the single generated ``LengthUnit`` type
(never re-declared — design §"where each piece lives", point 1).

Only the vocabulary lives here: the exact mm-per-unit conversion factors are a
frontend concern owned by ``packages/design`` (design §"where each piece lives",
point 2) — py-kit never converts, so no factor appears in this package.
"""

from typing import Literal

#: The length units a document may be displayed/authored in (design §1). ``mm``
#: is canonical storage; the rest are pure presentation.
LengthUnit = Literal["mm", "cm", "m", "in", "ft"]

#: The default document unit — canonical millimetres. Backward compatible: a
#: document created without a unit (and every pre-units row, backfilled by the
#: migration) reads back ``"mm"``, so nothing observable changes until a user
#: picks another unit (design §1).
DEFAULT_LENGTH_UNIT: LengthUnit = "mm"
