"""Assembly evaluation pipeline — dedup, diagnosis, and the error posture
(design ``assemblies.md`` §4/§6, the v1 DoD).

The golden (:mod:`tests.test_assembly_goldens`) locks the exact bolted transforms
+ combined roll-up + determinism; this module exercises the pipeline's BEHAVIOURS
that are not a single analytic transform: shared-mesh dedup (§6.4), the
under/conflicting diagnosis (§2.4/§6.3), and the never-500 per-instance/per-mate
error posture (§4) — a bodyless part, an unresolvable mate, an ungrounded
assembly. Requests are built programmatically from the committed plate part
(the sketch-extrude-plate-2holes golden), deriving mate signatures from the
evaluated body exactly as the selection overlay would (pick side == resolve
side), so no signature is hand-authored.

The OCP wheel ships no type stubs, so the raw ``BRepAdaptor_Curve`` call used to
locate a hole rim is opaque to pyright; the directive scopes that relaxation to
this test only, matching the kernel modules it exercises.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import uuid
from pathlib import Path

from build123d import GeomType, Solid
from geometry.assembly import evaluate_assembly
from geometry.features import evaluate_tree
from geometry.kernel.edges import edge_signature_dto
from geometry.kernel.faces import face_signature_dto, planar_faces
from OCP.BRepAdaptor import BRepAdaptor_Curve
from py_kit.schemas.assemblies import (
    CoincidentMate,
    ConcentricMate,
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    EvaluatedMate,
    MateAxisRef,
    MateFaceRef,
    Placement,
    Quat,
)
from py_kit.schemas.features import (
    EdgeSignature,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    PlanarFaceSignature,
    SketchFeature,
)
from py_kit.schemas.geometry import Vec3

TOL = 1e-6
TOP_Z = 10.0
HOLE_1 = (12.0, 12.5)
HOLE_2 = (28.0, 12.5)

_PLATE_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens/sketch-extrude-plate-2holes-40x25x10/model.json"
)


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _plate_features() -> list[EvaluatedFeatureInput]:
    """The committed plate-with-2-holes part's ordered feature list."""
    return EvaluateTreeRequest.model_validate_json(
        _PLATE_MODEL.read_text(encoding="utf-8")
    ).features


def _plate_body() -> Solid:
    body = evaluate_tree(
        EvaluateTreeRequest(part_id=iid(1), tree_version=1, features=_plate_features())
    ).body
    assert isinstance(body, Solid)  # single-body plate (§MB-0: bodies has 1 entry)
    return body


def _sketch_only_features() -> list[EvaluatedFeatureInput]:
    """A part with a sketch but NO body-affecting feature → evaluates to no body."""
    sketch = next(f for f in _plate_features() if isinstance(f.feature, SketchFeature))
    return [sketch]


def _face_sig(body: Solid, nz: float) -> PlanarFaceSignature:
    for record in planar_faces(body):
        sig = record.signature
        if abs(sig.normal.z - nz) < TOL and abs(sig.normal.x) < TOL:
            got = face_signature_dto(record.face)
            assert got is not None
            return got
    raise AssertionError(f"no planar face with normal z ~ {nz}")


def _hole_sig(body: Solid, cx: float, cy: float, cz: float) -> EdgeSignature:
    for edge in body.edges():
        if edge.geom_type != GeomType.CIRCLE:
            continue
        loc = BRepAdaptor_Curve(edge.wrapped).Circle().Location()
        if (
            abs(loc.X() - cx) < TOL
            and abs(loc.Y() - cy) < TOL
            and abs(loc.Z() - cz) < TOL
        ):
            return edge_signature_dto(edge)
    raise AssertionError(f"no circular edge at ({cx}, {cy}, {cz})")


def _instance(
    n: int,
    part_key: str,
    features: list[EvaluatedFeatureInput],
    *,
    grounded: bool,
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
    quat: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
) -> EvaluatedInstance:
    return EvaluatedInstance(
        instance_id=iid(n),
        part_key=part_key,
        features=features,
        placement=Placement(
            position=Vec3(x=pos[0], y=pos[1], z=pos[2]),
            orientation=Quat(x=quat[0], y=quat[1], z=quat[2], w=quat[3]),
        ),
        grounded=grounded,
    )


def _coincident(
    mate_id: int,
    order: int,
    top: PlanarFaceSignature,
    bottom: PlanarFaceSignature,
    a: int,
    b: int,
) -> EvaluatedMate:
    return EvaluatedMate(
        mate_id=iid(mate_id),
        order_index=order,
        mate=CoincidentMate(
            a=MateFaceRef(instance_id=iid(a), signature=top),
            b=MateFaceRef(instance_id=iid(b), signature=bottom),
            flush=True,
        ),
    )


def _concentric(
    mate_id: int,
    order: int,
    sa: EdgeSignature,
    sb: EdgeSignature,
    a: int,
    b: int,
) -> EvaluatedMate:
    return EvaluatedMate(
        mate_id=iid(mate_id),
        order_index=order,
        mate=ConcentricMate(
            a=MateAxisRef(instance_id=iid(a), signature=sa),
            b=MateAxisRef(instance_id=iid(b), signature=sb),
        ),
    )


_PART_KEY = "plate@1"


def _bolted_request(
    mates: list[EvaluatedMate], *, b_grounded: bool = False, a_grounded: bool = True
) -> EvaluateAssemblyRequest:
    features = _plate_features()
    return EvaluateAssemblyRequest(
        assembly_id=iid(9000),
        version=1,
        instances=[
            _instance(1, _PART_KEY, features, grounded=a_grounded),
            _instance(
                2,
                _PART_KEY,
                features,
                grounded=b_grounded,
                pos=(3.0, 2.0, 16.0),
                quat=(0.0, 0.0, 0.05, 0.99875),
            ),
        ],
        mates=mates,
    )


# --- shared-mesh dedup (§6.4) ---------------------------------------------------


def test_two_instances_of_one_part_share_one_mesh() -> None:
    """The perf contract: the same part instanced twice yields ONE distinct
    ``part_mesh_glb_id`` referenced by both placements (design §6.4)."""
    body = _plate_body()
    top, bottom = _face_sig(body, 1.0), _face_sig(body, -1.0)
    h1 = _hole_sig(body, *HOLE_1, TOP_Z)
    h2 = _hole_sig(body, *HOLE_2, TOP_Z)
    result = evaluate_assembly(
        _bolted_request(
            [
                _coincident(1001, 0, top, bottom, 1, 2),
                _concentric(1002, 1, h1, h1, 1, 2),
                _concentric(1003, 2, h2, h2, 1, 2),
            ]
        )
    )
    assert result.status == "well_constrained"
    mesh_ids = [inst.part_mesh_glb_id for inst in result.instances]
    assert len(set(mesh_ids)) == 1, "both instances must share one content address"
    assert mesh_ids[0] is not None and mesh_ids[0] == mesh_ids[1]
    assert mesh_ids[0].startswith("sha256:")


# --- diagnosis (§2.4 / §6.3) ----------------------------------------------------


def test_single_concentric_is_under_constrained_with_dof() -> None:
    """One hole leaves DOF (slide along + spin about the axis): NON-fatal
    under_constrained with a reported remaining_dof (design §2.4)."""
    body = _plate_body()
    h1 = _hole_sig(body, *HOLE_1, TOP_Z)
    result = evaluate_assembly(_bolted_request([_concentric(1002, 0, h1, h1, 1, 2)]))
    assert result.status == "under_constrained"
    assert result.diagnosis is not None
    assert result.diagnosis.remaining_dof > 0
    # The assembly still renders both instances (best-fit at seed).
    assert all(inst.error is None for inst in result.instances)
    assert all(inst.part_mesh_glb_id is not None for inst in result.instances)


def test_conflicting_mates_are_named_and_fatal_flavoured() -> None:
    """One hole of B forced collinear with BOTH of A's (16 mm apart) holes is
    unsatisfiable → conflicting, with the offending mate ids named (design §2.4)."""
    body = _plate_body()
    top, bottom = _face_sig(body, 1.0), _face_sig(body, -1.0)
    h1 = _hole_sig(body, *HOLE_1, TOP_Z)
    h2 = _hole_sig(body, *HOLE_2, TOP_Z)
    result = evaluate_assembly(
        _bolted_request(
            [
                _coincident(1001, 0, top, bottom, 1, 2),
                _concentric(1002, 1, h1, h1, 1, 2),  # B-hole1 ↔ A-hole1
                _concentric(1003, 2, h2, h1, 1, 2),  # B-hole1 ↔ A-hole2 (conflict)
            ]
        )
    )
    assert result.status == "conflicting"
    assert result.diagnosis is not None
    assert result.diagnosis.conflicting_mates, "conflict must name offending mates"


# --- error posture: never a 500/hang (§4) ---------------------------------------


def test_bodyless_part_is_a_per_instance_error_not_a_crash() -> None:
    """An instance whose part evaluates to no body reports a per-instance error
    and is dropped from the solve; the grounded valid instance still places
    (design §4). Mates onto the missing instance become per-mate errors."""
    body = _plate_body()
    top, bottom = _face_sig(body, 1.0), _face_sig(body, -1.0)
    features = _plate_features()
    request = EvaluateAssemblyRequest(
        assembly_id=iid(9001),
        version=1,
        instances=[
            _instance(1, _PART_KEY, features, grounded=True),
            _instance(
                2,
                "sketch-only@1",
                _sketch_only_features(),
                grounded=False,
                pos=(0.0, 0.0, 16.0),
            ),
        ],
        mates=[_coincident(1001, 0, top, bottom, 1, 2)],
    )
    result = evaluate_assembly(request)

    good = next(i for i in result.instances if i.instance_id == iid(1))
    bad = next(i for i in result.instances if i.instance_id == iid(2))
    assert good.error is None and good.part_mesh_glb_id is not None
    assert bad.error is not None and bad.error.code == "no_body"
    assert bad.part_mesh_glb_id is None
    # The mate onto the bodyless instance could not resolve → a per-mate error.
    assert any(me.mate_id == iid(1001) for me in result.mate_errors)


def test_unresolvable_mate_is_a_per_mate_error_and_dropped() -> None:
    """A mate with a stale face signature is a per-mate subshape_unresolved error
    and is DROPPED — the assembly still solves the mates it can (design §4)."""
    body = _plate_body()
    top = _face_sig(body, 1.0)
    stale = PlanarFaceSignature(
        normal=Vec3(x=0.0, y=0.0, z=-1.0),
        centroid=Vec3(x=20.0, y=12.5, z=99.0),  # no face at z=99
        area_mm2=760.7,
    )
    result = evaluate_assembly(
        _bolted_request([_coincident(1001, 0, top, stale, 1, 2)])
    )
    assert len(result.mate_errors) == 1
    assert result.mate_errors[0].mate_id == iid(1001)
    assert result.mate_errors[0].error.code == "subshape_unresolved"
    # Every mate dropped → the free instance is fully free (best-fit at seed).
    assert result.status == "under_constrained"
    assert all(inst.error is None for inst in result.instances)


def test_ungrounded_assembly_is_nonfatal_under_constrained() -> None:
    """No grounded instance → the whole rigid body floats: NON-fatal
    under_constrained by its 6 free DOF, rendered at seed (design §1.2)."""
    body = _plate_body()
    top, bottom = _face_sig(body, 1.0), _face_sig(body, -1.0)
    h1 = _hole_sig(body, *HOLE_1, TOP_Z)
    h2 = _hole_sig(body, *HOLE_2, TOP_Z)
    result = evaluate_assembly(
        _bolted_request(
            [
                _coincident(1001, 0, top, bottom, 1, 2),
                _concentric(1002, 1, h1, h1, 1, 2),
                _concentric(1003, 2, h2, h2, 1, 2),
            ],
            a_grounded=False,
            b_grounded=False,
        )
    )
    assert result.status == "under_constrained"
    assert result.diagnosis is not None
    assert result.diagnosis.remaining_dof >= 6
    assert all(inst.error is None for inst in result.instances)
    assert result.properties is not None  # still rolls up + renders


def test_self_mate_is_a_per_mate_error_not_a_500() -> None:
    """A mate whose two slots name the SAME instance resolves against the one
    body (so it passes the per-mate resolve guard) but the solver rejects it as
    self-referential. It must be DROPPED as a typed ``mate_self_reference``
    per-mate error inside a 200 — never a propagated AssemblyDefinitionError /
    500 — and the rest of the assembly still evaluates (design §4)."""
    body = _plate_body()
    top, bottom = _face_sig(body, 1.0), _face_sig(body, -1.0)
    h1 = _hole_sig(body, *HOLE_1, TOP_Z)
    h2 = _hole_sig(body, *HOLE_2, TOP_Z)
    # A valid coincident (1↔2) alongside a self-mate on instance 2 (2↔2): the
    # good mate must still be honoured, the self-mate dropped as a typed error.
    result = evaluate_assembly(
        _bolted_request(
            [
                _coincident(1001, 0, top, bottom, 1, 2),
                _concentric(1002, 1, h1, h1, 2, 2),  # self-mate: both slots = inst 2
                _concentric(1003, 2, h2, h2, 1, 2),  # valid A↔B mate
            ]
        )
    )
    offending = [me for me in result.mate_errors if me.mate_id == iid(1002)]
    assert len(offending) == 1
    assert offending[0].error.code == "mate_self_reference"
    # The self-mate is the ONLY per-mate error; the two valid mates are kept.
    assert [me.mate_id for me in result.mate_errors] == [iid(1002)]
    # The rest of the assembly still evaluated — every instance renders.
    assert all(inst.error is None for inst in result.instances)
    assert all(inst.part_mesh_glb_id is not None for inst in result.instances)


def test_duplicate_instance_id_is_a_clean_assembly_error_not_a_500() -> None:
    """Two instances sharing one ``instance_id`` is a malformed request the
    per-mate guards cannot catch — the pre-solve instance build raises
    AssemblyDefinitionError. It must map to a clean assembly-level status inside
    a 200 (never a propagated exception / 500), not a per-mate error (design
    §4)."""
    features = _plate_features()
    request = EvaluateAssemblyRequest(
        assembly_id=iid(9002),
        version=1,
        instances=[
            _instance(1, _PART_KEY, features, grounded=True),
            _instance(1, _PART_KEY, features, grounded=False),  # duplicate id
        ],
        mates=[],
    )
    # Driving evaluate_assembly directly: no exception may propagate.
    result = evaluate_assembly(request)
    assert result.status == "not_converged"
    assert result.diagnosis is not None
    assert "instance" in result.diagnosis.message.lower()
    # A malformed request, not a per-mate issue: nothing lands in mate_errors.
    assert result.mate_errors == []
