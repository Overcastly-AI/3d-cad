"""An assembly exported from a script says what it left out (ASM-FAILED-PART-API).

The bike, small: a frame that builds and a crank arm placed twice whose tree
builds no body (a sketch with nothing made from it — the bike's crank arm failed
with `profile_unsupported`; any part without a body is the same to an export).
The STEP holds the frame only, and a script that got it with no signal would
ship a short assembly: the export warns, naming the arm and both occurrences.
"""

from __future__ import annotations

import itertools
import warnings
from pathlib import Path

import loft
import pytest
from loft import _operations as ops
from loft_wire.assemblies import (
    AssemblyCreate,
    AssemblyResponse,
    InstanceCreate,
    InstanceMutationResponse,
)

from .conftest import Stack

PASSWORD = "assembly-export-passphrase"
_emails = (f"assembly-export-{n}@example.com" for n in itertools.count())


def _assembly(session: loft.Session, parts: list[tuple[loft.Part, str]]) -> str:
    """An assembly placing *parts* (the first grounded), through the gateway."""
    transport = session.transport
    created = transport.call(
        ops.POST_ASSEMBLIES, AssemblyResponse, body=AssemblyCreate(name="Bike")
    )
    version = created.doc_version
    for n, (part, name) in enumerate(parts):
        added = transport.call(
            ops.POST_ASSEMBLIES_ASSEMBLY_ID_INSTANCES,
            InstanceMutationResponse,
            path_params={"assembly_id": created.id},
            body=InstanceCreate(
                expected_version=version,
                ref_document_id=part.id,
                ref_document_kind="part",
                name=name,
                grounded=n == 0,
            ),
        )
        version = added.doc_version
    return str(created.id)


def _frame(session: loft.Session) -> loft.Part:
    frame = session.new_part("Frame")
    sk = frame.sketch(on="XY")
    sk.rect(40, 20)
    sk.solve()
    frame.extrude(sk, 5)
    return frame


def test_exporting_the_bike_warns_naming_both_crank_arms(
    stack: Stack, tmp_path: Path
) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        arm = session.new_part("Crank arm")
        sk = arm.sketch(on="XY")
        sk.rect(30, 8)
        sk.solve()  # a profile, and nothing made from it: no body
        bike = session.assembly(
            _assembly(
                session,
                [
                    (_frame(session), "Frame <1>"),
                    (arm, "Crank arm <1>"),
                    (arm, "Crank arm <2>"),
                ],
            )
        )

        with pytest.warns(loft.OmittedOccurrencesWarning) as caught:
            written = bike.export(tmp_path / "bike.step")

        [warning] = caught.list
        assert isinstance(warning.message, loft.OmittedOccurrencesWarning)
        message = str(warning.message)
        assert message.startswith("bike.step leaves out 2 occurrences"), message
        assert "Crank arm x2" in message, message
        omitted = warning.message.omitted
        assert omitted.count == 2
        assert [(p.name, p.occurrences) for p in omitted.parts] == [("Crank arm", 2)]
        assert str(omitted.parts[0].part_document_id) == str(arm.id)
        # The file is still written, holding the frame alone.
        assert written.read_bytes().count(b"NEXT_ASSEMBLY_USAGE_OCCURRENCE(") == 1


def test_a_healthy_assembly_exports_without_a_warning(stack: Stack) -> None:
    with loft.register(
        stack.gateway_url, email=next(_emails), password=PASSWORD
    ) as session:
        frame = _frame(session)
        bike = session.assembly(
            _assembly(session, [(frame, "Frame <1>"), (frame, "Frame <2>")])
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", loft.OmittedOccurrencesWarning)
            data = bike.export_bytes("step")
        assert data.count(b"NEXT_ASSEMBLY_USAGE_OCCURRENCE(") == 2
