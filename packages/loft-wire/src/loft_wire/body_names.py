"""Body names (BODY-NAMES): what the browser, the tree and a STEP file call a body.

Fusion names every body in its browser, and so does Loft:

- A plugin member's body is named after its feature and its member, as the
  unfolded tree names the member: ``"Front wall · Stud 3"``, or
  ``"Roof · Ridge"`` when its title has one member (:func:`member_body_names`).
  The number counts, in expansion order, the feature's members whose roles
  share the title, so two roles titled "Stud" give Stud 1..11, never two
  "Stud 1"; the same inputs expand in the same order, so it is deterministic.
  A rename keys on the member id, never on this number.
- Any other body keeps its current name ("Body 2" in the browser, no name of
  its own in a STEP file).
- A user's rename wins over both and is stored on the part as a
  :class:`BodyName` keyed by the body's identity, the id of the feature (or
  member) that created it, as a per-body material override is.

A name is display metadata, never an input to geometry: renaming a body
changes no shape and leaves the part's last evaluate current.
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
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


def member_body_name(feature_name: str, title: str, place: int, count: int) -> str:
    """A plugin member's body name: ``"<feature> · <title> <place + 1>"``, the
    number left out when *count*, the members sharing the title, is one."""
    label = f"{title} {place + 1}" if count > 1 else title
    return f"{feature_name}{BODY_NAME_SEPARATOR}{label}"[:BODY_NAME_MAX_LENGTH]


def member_body_names(
    feature_name: str,
    members: Sequence[tuple[uuid.UUID, str]],
    titles: Mapping[str, str],
    fallback: Callable[[str], str] = str,
) -> list[BodyName]:
    """Every member's body name, in expansion order. *members* are each
    member's id and role; *titles* titles a role (*fallback* one it lacks).
    Numbered across the roles that share a title, exactly as the unfolded
    tree labels the members (``apps/web/src/features/customFeature.ts``,
    ``memberLabels``)."""
    titled = [titles.get(role) or fallback(role) for _, role in members]
    counts: dict[str, int] = {}
    for title in titled:
        counts[title] = counts.get(title, 0) + 1
    seen: dict[str, int] = {}
    out: list[BodyName] = []
    for (member_id, _), title in zip(members, titled, strict=True):
        place = seen.get(title, 0)
        seen[title] = place + 1
        name = member_body_name(feature_name, title, place, counts[title])
        out.append(BodyName(base_feature_id=member_id, name=name))
    return out


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
