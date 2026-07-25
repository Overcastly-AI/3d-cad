"""Assembly-import boundary DTOs — the shared-body transport shape.

The reshape that carries each product B-rep ONCE per ``body_step_id`` (BACKLOG
P2, transport efficiency + defence in depth). These tests own the contract every
service on the chain relies on: the geometry reader may attach a body to each
product it walks, but the SERIALIZED result carries each distinct body exactly
once in ``bodies`` — so a part instanced N times ships its (multi-MB) STEP
fragment once, not N times — and every consumer resolves through the ONE
resolver, :meth:`StepAssemblyImportResult.body_step_for`.
"""

import json

from py_kit.schemas.assemblies import Placement, Quat
from py_kit.schemas.geometry import Vec3
from py_kit.schemas.step_import import (
    ImportedProduct,
    StepAssemblyImportResult,
)

BODY_A = "sha256:" + "a" * 64
BODY_B = "sha256:" + "b" * 64
STEP_A = "ISO-10303-21;\nDATA;\n/* body A */\nENDSEC;\n"
STEP_B = "ISO-10303-21;\nDATA;\n/* body B */\nENDSEC;\n"

IDENTITY = Placement(position=Vec3(x=0, y=0, z=0), orientation=Quat(x=0, y=0, z=0, w=1))


def _product(
    *, name: str, body_id: str | None, body_step: str | None
) -> ImportedProduct:
    return ImportedProduct(
        name=name,
        placement=IDENTITY,
        body_step=body_step,
        body_step_id=body_id,
        mesh_glb_id=None,
    )


def _repeated_part_read() -> StepAssemblyImportResult:
    """Two occurrences of ONE body plus a second distinct body (the dedup shape)."""
    return StepAssemblyImportResult(
        has_assembly_structure=True,
        products=[
            _product(name="Bracket", body_id=BODY_A, body_step=STEP_A),
            _product(name="Bracket", body_id=BODY_A, body_step=STEP_A),
            _product(name="Pin", body_id=BODY_B, body_step=STEP_B),
        ],
    )


def test_producer_bodies_are_hoisted_and_deduped_by_address() -> None:
    """A producer attaching bodies per product yields ONE entry per address."""
    read = _repeated_part_read()
    assert read.bodies == {BODY_A: STEP_A, BODY_B: STEP_B}


def test_serialized_result_carries_each_body_once() -> None:
    """THE point of the reshape: 3 products, 2 bodies on the wire (no per-product).

    The repeated part's fragment appears exactly once in the JSON, and no product
    object carries a ``body_step`` key at all — the amplification is gone from the
    transport, not merely bounded by ``MAX_IMPORT_RESPONSE_BYTES``.
    """
    payload = _repeated_part_read().model_dump_json()
    assert payload.count(json.dumps(STEP_A)[1:-1]) == 1
    body = json.loads(payload)
    assert set(body["bodies"]) == {BODY_A, BODY_B}
    assert [product["body_step_id"] for product in body["products"]] == [
        BODY_A,
        BODY_A,
        BODY_B,
    ]
    assert all("body_step" not in product for product in body["products"])


def test_round_trip_through_json_resolves_bodies() -> None:
    """A consumer validating the wire form resolves each product's body by id."""
    wire = _repeated_part_read().model_dump_json()
    read = StepAssemblyImportResult.model_validate_json(wire)
    assert [read.body_step_for(product) for product in read.products] == [
        STEP_A,
        STEP_A,
        STEP_B,
    ]
    # Bodies really are shared, not copies: one map entry serves both occurrences.
    assert len(read.bodies) == 2


def test_explicit_bodies_map_is_authoritative_over_a_product_field() -> None:
    """A caller may build the canonical shape directly (bodies + id references)."""
    read = StepAssemblyImportResult(
        has_assembly_structure=True,
        products=[_product(name="Bracket", body_id=BODY_A, body_step=None)],
        bodies={BODY_A: STEP_A},
    )
    assert read.body_step_for(read.products[0]) == STEP_A
    # An explicit entry wins over a stale/conflicting producer-side attachment.
    conflicting = StepAssemblyImportResult(
        has_assembly_structure=True,
        products=[_product(name="Bracket", body_id=BODY_A, body_step=STEP_B)],
        bodies={BODY_A: STEP_A},
    )
    assert conflicting.bodies == {BODY_A: STEP_A}


def test_unresolvable_and_bodyless_products_resolve_to_none() -> None:
    """No address (no solid) or an address absent from the map → ``None``.

    The resolver never guesses: a malformed read is "not importable", which lets
    each consumer surface its own typed error (documents' ``import_no_solid``)
    instead of trusting a partial map.
    """
    read = StepAssemblyImportResult(
        has_assembly_structure=True,
        products=[
            _product(name="Empty", body_id=None, body_step=None),
            _product(name="Dangling", body_id=BODY_B, body_step=None),
        ],
        bodies={BODY_A: STEP_A},
    )
    assert [read.body_step_for(product) for product in read.products] == [None, None]
