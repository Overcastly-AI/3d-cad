"""Body names (BODY-NAMES): what the browser, the tree and a STEP file call a body.

Fusion names every body in its browser, and so does Loft:

- A plugin member's body is named after its feature and its member, as the
  unfolded tree names the member: ``"Front wall · Stud 3"``, or
  ``"Roof · Ridge"`` when the role has one member (:func:`member_body_name`).
  The number is the member's place in its role (``index + 1``), which the
  stable member names keep for the same inputs (RESEARCH §23).
- Any other body keeps its current name ("Body 2" in the browser, no name of
  its own in a STEP file).
- A user's rename wins over both and is stored on the part as a
  :class:`BodyName` keyed by the body's identity, the id of the feature (or
  member) that created it, as a per-body material override is.

A name is display metadata, never an input to geometry: renaming a body
changes no shape and leaves the part's last evaluate current.
"""

import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

#: The longest body name: a feature name (200), the separator, a role title
#: and a number, with room to spare. A user's rename is held to the same.
BODY_NAME_MAX_LENGTH = 400

#: At most one name per body, and a part has at most one body per feature, so
#: this is ``loft_wire.features.MAX_TREE_FEATURES`` (asserted by the tests;
#: not imported, because ``features`` imports this module).
MAX_BODY_NAMES = 1000

#: The separator between the feature and the member, as the cut list and the
#: rest of the interface join two names.
BODY_NAME_SEPARATOR = " · "

BodyNameText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=BODY_NAME_MAX_LENGTH
    ),
]


class BodyName(BaseModel):
    """One body's name, keyed by the body's identity (multi-body §MB-0)."""

    base_feature_id: uuid.UUID = Field(
        description="Id of the feature (or plugin member) that created the body"
    )
    name: BodyNameText = Field(description="The body's name, whitespace-trimmed")


def _one_per_body(names: list[BodyName]) -> list[BodyName]:
    """Refuse two names for one body: "last wins" would make the name depend
    on array order (RESEARCH §9)."""
    seen: set[uuid.UUID] = set()
    for entry in names:
        if entry.base_feature_id in seen:
            raise ValueError(f"duplicate name for body {entry.base_feature_id}")
        seen.add(entry.base_feature_id)
    return names


#: A part's names, at most one per body.
BodyNameList = Annotated[
    list[BodyName],
    Field(max_length=MAX_BODY_NAMES),
    AfterValidator(_one_per_body),
]


class PartBodyNames(BaseModel):
    """``GET /parts/{id}/body-names`` (documents, internal): every named body of
    the part's evaluated tree, a user's rename winning over a member's name.
    A body with neither is left out; it keeps its current name."""

    bodies: BodyNameList = Field(default_factory=list[BodyName])


def member_body_name(feature_name: str, title: str, index: int, role_count: int) -> str:
    """A plugin member's body name: ``"<feature> · <title> <n>"``, the number
    left out when the role has one member, exactly as the unfolded tree labels
    the member (``apps/web/src/features/customFeature.ts``, ``memberLabel``)."""
    label = f"{title} {index + 1}" if role_count > 1 else title
    return f"{feature_name}{BODY_NAME_SEPARATOR}{label}"[:BODY_NAME_MAX_LENGTH]


def solid_names(
    bodies: list[tuple[uuid.UUID, int]], names: list[BodyName]
) -> list[str | None] | None:
    """One name per solid of an evaluated body set, in its order, or ``None``
    when no body is named. *bodies* is each body's id and lump count in
    evaluation order (``EvaluateTreeResult.bodies``): a body of several lumps
    names each of them."""
    by_id = {entry.base_feature_id: entry.name for entry in names}
    out: list[str | None] = []
    for body_id, lumps in bodies:
        out.extend([by_id.get(body_id)] * lumps)
    return out if any(name is not None for name in out) else None
