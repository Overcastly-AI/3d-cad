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
   can see that twenty dowel pins are one part, audit N8); 3MF as one NAMED
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

from py_kit.schemas.assemblies import (
    ExportAssemblyRequest,
    assembly_export_root_name,
)

from geometry.assembly.evaluate import PlacedInstance, solve_assembly
from geometry.assembly.transform import Pose
from geometry.kernel import (
    AssemblyComponent,
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


def _component(placed: PlacedInstance) -> AssemblyComponent:
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
    )


def export_assembly(request: ExportAssemblyRequest) -> bytes:
    """Evaluate + solve *request* and export it as one multi-instance CAD file.

    Reuses :func:`solve_assembly` (identical to the evaluate path), then composes
    every instance that produced a body — at its SOLVED world placement — into a
    single STEP (AP214 product structure, named PRODUCTs) or STL (faceted
    compound). Deterministic end to end (RESEARCH §9; module docstring).

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
    components = [_component(placed) for placed in solved.placed]
    match request.format:
        case "step":
            return export_step_assembly_bytes(
                assembly_export_root_name(request), components
            )
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
