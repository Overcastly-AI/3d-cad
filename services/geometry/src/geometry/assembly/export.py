"""Assembly export — compose a solved assembly into ONE multi-instance CAD file.

The interop sibling of the part-level export (``geometry.kernel.export`` /
``POST /api/v1/export``): where :func:`~geometry.assembly.evaluate.evaluate_assembly`
returns per-instance ``{shared mesh, solved placement}`` for the viewport, this
path composes the SAME solved graph into a single downloadable file (RESEARCH
§10/§11 — assemblies are "a one-way street" until they export).

Pipeline (reusing the shipped solve VERBATIM):

1. :func:`~geometry.assembly.evaluate.solve_assembly` — evaluate each unique part
   once + solve the mate graph → each instance's resolved kernel body paired with
   its SOLVED world placement (the exact core ``evaluate_assembly`` serialises).
2. Hand each placed body + its instance name to the kernel composer
   (:func:`~geometry.kernel.export.export_step_assembly_bytes` /
   ``export_stl_assembly_bytes`` / ``export_3mf_assembly_bytes`` /
   ``export_glb_assembly_bytes``), which positions every body and writes ONE
   file. How much of the assembly's STRUCTURE survives is the format's, not
   ours: STEP as **INSTANCED AP214 product structure** (each unique PART is one
   named PRODUCT, placed once per instance as a named occurrence — so a
   re-import recovers every body traceable to its instance AND a downstream tool
   can see that twenty dowel pins are one part, audit N8; each sub-assembly is a
   nested PRODUCT holding its own occurrences, placed relative to it, as
   SolidWorks and Fusion write it, BIKE2-STEP-FLAT); 3MF as one NAMED
   OBJECT per instance (structure, no instancing); STL and GLB as one faceted
   compound with placements baked in and nothing else kept.

The file is named after the ASSEMBLY, root PRODUCT and download alike
(``assembly_export_root_name`` / ``assembly_export_filename``, audit N4), falling
back to the assembly id when the request carries no name.

No kernel type crosses the boundary — the caller gets bytes. Deterministic
(RESEARCH §9): the solve is BLAS-pinned, the STEP timestamp is pinned, the
per-occurrence id counter is canonicalised, and the 3MF production-extension
UUIDs are pinned, so the same graph in yields identical bytes out. An assembly
where NO instance produced a body is a clean
:class:`AssemblyExportError` (mapped to a 422 by the API layer), never a
zero-solid file or a 500 — mirroring the tree-export no-body posture (§4.3).
"""

from __future__ import annotations

import uuid

from loft_wire.assemblies import (
    EvaluateAssemblyRequest,
    ExportAssemblyRequest,
    Placement,
    assembly_export_root_name,
)
from loft_wire.omitted_occurrences import (
    OmittedOccurrences,
)

from geometry.assembly.evaluate import (
    Occurrence,
    PlacedInstance,
    SolvedAssembly,
    iter_part_instances,
    solve_assembly,
)
from geometry.assembly.mirrors import mirrored_name, source_part_key
from geometry.assembly.transform import Pose
from geometry.features.evaluate import features_have_twist
from geometry.kernel import (
    AssemblyComponent,
    StepAssemblyItem,
    SubAssemblyComponent,
    export_3mf_assembly_bytes,
    export_glb_assembly_bytes,
    export_step_assembly_bytes,
    export_stl_assembly_bytes,
)


class AssemblyExportError(Exception):
    """No instance produced a body, so there is nothing to export (design §4).

    Carries a legible ``code`` (``assembly_export_no_body``) the API layer maps
    to a clean 422 envelope — a body-less assembly is never a zero-solid file or
    a 500 (mirroring ``tree_export_failed``).
    """

    def __init__(self, message: str, *, code: str = "assembly_export_no_body") -> None:
        super().__init__(message)
        self.code = code


def _pose_fields(
    placement: Placement,
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """*placement* as the kernel's ``(translation, (x, y, z, w))`` pair."""
    pose = Pose.from_placement(placement)
    return (
        (float(pose.t[0]), float(pose.t[1]), float(pose.t[2])),
        (float(pose.q[0]), float(pose.q[1]), float(pose.q[2]), float(pose.q[3])),
    )


def _copy_name(name: str | None, index: int) -> str | None:
    """A pattern copy's name: its seed's, numbered within the pattern (the
    evaluate path's rule for a part copy, applied to a sub-assembly copy)."""
    return None if name is None else f"{name} ({index + 1})"


def _sub_assembly_item(
    group_id: uuid.UUID,
    members: list[Occurrence],
    solved: SolvedAssembly,
    request: EvaluateAssemblyRequest,
    twisted_parts: set[str],
) -> SubAssemblyComponent | None:
    """One sub-assembly occurrence of *request* (an instance, or a pattern copy
    or mirror twin of one), with its own level rebuilt from that
    sub-assembly's solve.

    Its pose in this level's frame is the instance's solved pose; a copy has
    none of its own, so it is read off a member: the member's pose here
    composed with the inverse of its pose inside the sub-assembly (``offset``).
    ``None`` when nothing inside it produced a body.
    """
    by_id = {inst.instance_id: inst for inst in request.instances}
    first = members[0]
    inst = by_id.get(group_id)
    if inst is not None:
        name = inst.name
        placement = solved.sub_assembly_poses.get(group_id, inst.placement)
    else:
        if first.pattern is not None:
            inst = by_id[first.pattern.seed_instance_id]
            name = _copy_name(inst.name, first.pattern.index)
        else:
            assert first.mirror is not None, (
                "a sub-assembly group is an instance, a copy or a twin"
            )
            inst = by_id[first.mirror.seed_instance_id]
            name = mirrored_name(inst.name, opposite=False)
        assert first.offset is not None
        frame = Pose.from_placement(first.placement).compose(first.offset.inverse())
        placement = frame.to_placement()
    assert inst.sub_assembly is not None
    children = _step_items(solved.subs[inst.part_key], inst.sub_assembly, twisted_parts)
    if not children:
        return None
    translation, quaternion = _pose_fields(placement)
    return SubAssemblyComponent(
        name=name if name is not None else str(group_id),
        key=inst.part_key,
        translation=translation,
        quaternion=quaternion,
        children=tuple(children),
    )


def _step_items(
    solved: SolvedAssembly,
    request: EvaluateAssemblyRequest,
    twisted_parts: set[str],
) -> list[StepAssemblyItem]:
    """*request*'s level of the STEP product tree, in occurrence order
    (BIKE2-STEP-FLAT).

    The solve flattens every sub-assembly into its parent's occurrences; they
    are grouped back here by the instance (or pattern copy) they move with. A
    group with no path is a part placed at this level, in this level's frame;
    any other group is a sub-assembly, rebuilt from its own solve (``subs`` is
    one dict shared by every level of the tree). Composing the levels' poses
    gives back each part's solved world placement.
    """
    groups: dict[uuid.UUID, list[Occurrence]] = {}
    for occ in solved.occurrences:
        groups.setdefault(occ.group_id, []).append(occ)
    items: list[StepAssemblyItem] = []
    for group_id, members in groups.items():
        first = members[0]
        if first.path:
            sub = _sub_assembly_item(group_id, members, solved, request, twisted_parts)
            if sub is not None:
                items.append(sub)
            continue
        if first.body is None:
            continue
        translation, quaternion = _pose_fields(first.placement)
        items.append(
            AssemblyComponent(
                name=first.name if first.name is not None else str(group_id),
                body=first.body,
                translation=translation,
                quaternion=quaternion,
                twisted=source_part_key(first.part_key) in twisted_parts,
            )
        )
    return items


def _component(placed: PlacedInstance, twisted_parts: set[str]) -> AssemblyComponent:
    """A solved instance as a kernel :class:`AssemblyComponent` (name + world pose).

    The instance's HUMAN-READABLE name (``PlacedInstance.name``) names the STEP
    occurrence, and — with its ``<n>`` suffix stripped — the shared PRODUCT, so a
    Loft->STEP->Loft round trip recovers the real names rather than the instance
    UUID (FINDINGS #7, audit N8); a request that carries no name falls back to
    the instance id (still traceable, never a nameless occurrence). The world
    placement is decomposed into a translation + unit
    quaternion via the same :class:`Pose` the solver uses, so no representation
    drift happens between solve and export.
    """
    pose = Pose.from_placement(placed.placement)
    return AssemblyComponent(
        name=placed.name if placed.name is not None else str(placed.instance_id),
        body=placed.body,
        translation=(float(pose.t[0]), float(pose.t[1]), float(pose.t[2])),
        quaternion=(
            float(pose.q[0]),
            float(pose.q[1]),
            float(pose.q[2]),
            float(pose.q[3]),
        ),
        twisted=source_part_key(placed.part_key) in twisted_parts,
    )


def export_assembly(request: ExportAssemblyRequest) -> bytes:
    """The file :func:`export_assembly_reporting` writes, without the report."""
    data, _omitted = export_assembly_reporting(request)
    return data


def export_assembly_reporting(
    request: ExportAssemblyRequest,
) -> tuple[bytes, OmittedOccurrences | None]:
    """Evaluate + solve *request* and export it as one multi-instance CAD file.

    Reuses :func:`solve_assembly` (identical to the evaluate path), then composes
    every instance that produced a body — at its SOLVED world placement — into a
    single STEP (AP214 product structure, named PRODUCTs) or STL (faceted
    compound). Deterministic end to end (RESEARCH §9; module docstring).

    Returns the file and the occurrences it LEFT OUT (their part produced no
    body; :func:`~geometry.assembly.evaluate.omitted_occurrences`), None when
    the file holds every occurrence (ASM-FAILED-PART-API).

    Raises:
        AssemblyExportError: no instance produced a body (nothing to export); the
            API layer maps it to a clean 422 ``assembly_export_no_body`` envelope.
    """
    solved = solve_assembly(request)
    if not solved.placed:
        raise AssemblyExportError(
            "No instance in the assembly produced a body; there is nothing to "
            "export. Check the parts' feature trees for errors."
        )
    # Parts with a twisted extrude mesh their flanks with the bounded mesher
    # in the mesh exports, as the single-part export does
    # (TWIST-ASSEMBLY-MESH-COST-1; design twisted-extrude.md §6.1).
    twisted_parts = {
        instance.part_key
        for instance in iter_part_instances(request.instances)
        if features_have_twist(instance.features)
    }
    return _write(request, solved, twisted_parts), solved.omitted()


def _write(
    request: ExportAssemblyRequest, solved: SolvedAssembly, twisted_parts: set[str]
) -> bytes:
    """The file in *request*'s format, from the solved bodies."""
    if request.format == "step":
        return export_step_assembly_bytes(
            assembly_export_root_name(request),
            _step_items(solved, request, twisted_parts),
        )
    components = [_component(placed, twisted_parts) for placed in solved.placed]
    match request.format:
        case "stl":
            return export_stl_assembly_bytes(
                components, request.linear_deflection, request.angular_deflection
            )
        case "3mf":
            return export_3mf_assembly_bytes(
                components, request.linear_deflection, request.angular_deflection
            )
        case "glb":
            return export_glb_assembly_bytes(components, request.linear_deflection)
