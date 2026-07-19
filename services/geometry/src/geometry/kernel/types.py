"""Shared kernel body type — a part's body is a solid or a compound of solids.

Multi-body (docs/design/multi-body.md §MB-0): a part may end with more than one
disjoint body, so every kernel entry point that used to take a single
:class:`~build123d.Solid` now takes a :data:`BodyShape` — a single ``Solid`` OR a
:class:`~build123d.Compound` of the part's disjoint solids. Both are CONCRETE
build123d types (unlike the generic base ``Shape[TOPODS]``, which pyright reads as
partially-unknown), so the union keeps callers fully typed. Defined in one leaf
module (CLAUDE.md DRY rule) that only imports build123d, so the low-level
resolvers (:mod:`geometry.kernel.faces`, :mod:`geometry.kernel.edges`) and the
package ``__init__`` can all reference it without an import cycle.
"""

from build123d import Compound, Solid

#: A part body handed to a kernel resolver / measurer / exporter: a single
#: :class:`~build123d.Solid`, or a :class:`~build123d.Compound` of a multi-body
#: part's disjoint solids (§MB-0). ``.faces()`` / ``.edges()`` / ``.solids()``
#: iterate every subshape solid, so a resolver written against one body works
#: unchanged over the compound.
BodyShape = Solid | Compound
