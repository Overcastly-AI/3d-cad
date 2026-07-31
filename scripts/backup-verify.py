#!/usr/bin/env python3
"""Seed real data, then prove it SURVIVED a backup → destroy → restore cycle.

Two legs of one drill (``scripts/backup-restore-drill.sh``), over the published
gateway port and nothing else — exactly the surface a browser uses::

    python3 scripts/backup-verify.py seed   --state-out /tmp/state.json
    python3 scripts/backup-verify.py verify --state-in  /tmp/state.json \\
        --assert-cold-object-store

**seed** registers a user, authors a part (sketch + extrude, the shared 40 x 25
x 10 mm block), evaluates it, and builds the other two document kinds a real
install holds — an assembly with an instance of that part, and a drawing with a
sheet and a view of it. It records the ids, the evaluated **volume** and the
content-addressed **mesh id** into a state file.

**verify** logs in as the SAME user with the SAME password (so the restore is
proven to have carried the gateway's identity rows, not just the documents
ones), re-reads every document, and then **re-evaluates the part** and demands
the SAME volume and the SAME ``mesh_glb_id``. ``mesh_glb_id`` is the SHA-256 of
the tessellated GLB, so equality is a claim about bytes: the restored feature
tree re-derives a bit-identical solid. "The dump file is non-empty" proves
nothing; this proves the part is really back.

``--assert-cold-object-store`` additionally demands that the pre-backup mesh is
**gone** (404) *before* that re-evaluate. That is the drill's proof that the
destroy step really destroyed something — without it, a drill that silently
skipped ``docker compose down -v`` would pass on the surviving cache. It is a
flag rather than the default only so the legs can be rehearsed against a stack
that was never destroyed; the CI drill always passes it.

Exit code 0 = every assertion held; 1 = a named check failed.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any, cast

# Shared with scripts/compose-roundtrip.py — one definition of "a real modeling
# round-trip" (CLAUDE.md DRY). Hyphenated script names are not importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _selfhost_api import (
    DEPTH_MM,
    EXPECTED_VOLUME_MM3,
    VOLUME_RTOL,
    CheckFailed,
    assert_glb_has_geometry,
    expect,
    request,
    sketch_params,
)

#: State-file format marker, so a stale file from an older drill fails loudly
#: instead of half-matching.
STATE_FORMAT = "loft-backup-drill/1"


def _obj(value: Any, what: str) -> dict[str, Any]:
    """Narrow an untyped JSON member to an object (pyright-strict helper)."""
    if not isinstance(value, dict):
        raise CheckFailed(f"{what}: expected an object, got {value!r}")
    return cast("dict[str, Any]", value)


def _list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise CheckFailed(f"{what}: expected a list, got {value!r}")
    return cast("list[Any]", value)


def _author_part(base_url: str, token: str) -> dict[str, Any]:
    """Create a part with a sketch + extrude tree and evaluate it."""
    part = expect(
        request(
            base_url,
            "POST",
            "/api/v1/parts",
            token=token,
            payload={"name": "backup-drill-block"},
        ),
        201,
        "create part",
    )
    part_id = str(part["id"])

    sketch = expect(
        request(
            base_url,
            "POST",
            f"/api/v1/parts/{part_id}/features",
            token=token,
            payload={
                "name": "Sketch1",
                "feature": {"type": "sketch", "version": 1, "params": sketch_params()},
                "expected_tree_version": 0,
            },
        ),
        201,
        "create sketch feature",
    )
    sketch_id = str(_obj(sketch["feature"], "sketch feature")["id"])

    extrude = expect(
        request(
            base_url,
            "POST",
            f"/api/v1/parts/{part_id}/features",
            token=token,
            payload={
                "name": "Extrude1",
                "feature": {
                    "type": "extrude",
                    "version": 1,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": sketch_id},
                        "distance_mm": DEPTH_MM,
                        "operation": "add",
                        "direction": "normal",
                    },
                },
                "expected_tree_version": int(sketch["tree_version"]),
            },
        ),
        201,
        "create extrude feature",
    )
    return {
        "id": part_id,
        "name": "backup-drill-block",
        "sketch_id": sketch_id,
        "extrude_id": str(_obj(extrude["feature"], "extrude feature")["id"]),
        "tree_version": int(extrude["tree_version"]),
    }


def _evaluate(base_url: str, token: str, part_id: str) -> tuple[float, str]:
    """Evaluate a part; return (volume mm^3, mesh_glb_id). Every feature must be ok."""
    result = expect(
        request(base_url, "POST", f"/api/v1/parts/{part_id}/evaluate", token=token),
        200,
        "evaluate",
    )
    for entry in _list(result["features"], "evaluate features"):
        feature = _obj(entry, "feature result")
        if feature.get("status") != "ok":
            raise CheckFailed(
                f"feature {feature.get('name')} did not evaluate: {feature}"
            )
    mesh_id = result.get("mesh_glb_id")
    if not isinstance(mesh_id, str) or not mesh_id.startswith("sha256:"):
        raise CheckFailed(
            f"evaluate returned no content-addressed mesh id: {mesh_id!r}"
        )
    volume = float(_obj(result.get("properties"), "mass properties")["volume"])
    if abs(volume - EXPECTED_VOLUME_MM3) > VOLUME_RTOL * EXPECTED_VOLUME_MM3:
        raise CheckFailed(
            f"evaluated volume {volume} mm^3, expected {EXPECTED_VOLUME_MM3} mm^3"
        )
    return volume, mesh_id


def _fetch_mesh(base_url: str, token: str, mesh_id: str) -> bytes:
    mesh = request(base_url, "GET", f"/api/v1/geometry/meshes/{mesh_id}", token=token)
    if mesh.status != 200:
        raise CheckFailed(
            f"mesh fetch: expected HTTP 200, got {mesh.status} — {mesh.text()}"
        )
    assert_glb_has_geometry(mesh.body)
    return mesh.body


def _author_assembly(base_url: str, token: str, part_id: str) -> dict[str, Any]:
    """An assembly holding one instance of the part (the second document kind)."""
    assembly = expect(
        request(
            base_url,
            "POST",
            "/api/v1/assemblies",
            token=token,
            payload={"name": "backup-drill-assembly"},
        ),
        201,
        "create assembly",
    )
    assembly_id = str(assembly["id"])
    instance = expect(
        request(
            base_url,
            "POST",
            f"/api/v1/assemblies/{assembly_id}/instances",
            token=token,
            payload={
                "name": "Block-1",
                "ref_document_id": part_id,
                "ref_document_kind": "part",
                "grounded": True,
                "expected_version": int(assembly["doc_version"]),
            },
        ),
        201,
        "add assembly instance",
    )
    return {
        "id": assembly_id,
        "name": "backup-drill-assembly",
        "instance_id": str(_obj(instance["instance"], "instance")["id"]),
        "instance_name": "Block-1",
    }


def _author_drawing(base_url: str, token: str, part_id: str) -> dict[str, Any]:
    """A drawing with a sheet and a front view of the part (the third kind)."""
    drawing = expect(
        request(
            base_url,
            "POST",
            "/api/v1/drawings",
            token=token,
            payload={"name": "backup-drill-drawing"},
        ),
        201,
        "create drawing",
    )
    drawing_id = str(drawing["id"])
    sheet_response = expect(
        request(
            base_url,
            "POST",
            f"/api/v1/drawings/{drawing_id}/sheets",
            token=token,
            payload={
                "name": "Sheet1",
                "size": "A4",
                "orientation": "landscape",
                "expected_version": int(drawing["doc_version"]),
            },
        ),
        201,
        "create sheet",
    )
    sheet_id = str(_obj(sheet_response["sheet"], "sheet")["id"])
    view_response = expect(
        request(
            base_url,
            "POST",
            f"/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
            token=token,
            payload={
                "ref_document_id": part_id,
                "ref_document_kind": "part",
                "projection": "front",
                "position": {"x_mm": 90.0, "y_mm": 120.0},
                "expected_version": int(sheet_response["doc_version"]),
            },
        ),
        201,
        "create view",
    )
    return {
        "id": drawing_id,
        "name": "backup-drill-drawing",
        "sheet_id": sheet_id,
        "view_id": str(_obj(view_response["view"], "view")["id"]),
    }


def seed(base_url: str, state_path: Path) -> None:
    """Author a part + assembly + drawing and record what a restore must return."""
    steps: list[str] = []

    def ok(message: str) -> None:
        steps.append(message)
        print(f"  ok  {message}", flush=True)

    email = f"backup-drill-{uuid.uuid4().hex[:12]}@example.com"
    # Ephemeral, per-run, and only ever written to the drill's temp state file —
    # never to a committed file (compose-smoke.sh's rule for datastore creds).
    password = f"drill-{secrets.token_hex(16)}"
    registered = expect(
        request(
            base_url,
            "POST",
            "/api/v1/auth/register",
            payload={"email": email, "password": password},
        ),
        201,
        "register",
    )
    token = str(registered["access_token"])
    ok(f"registered {email}")

    part = _author_part(base_url, token)
    ok(f"authored part {part['id']} (sketch + extrude)")

    volume, mesh_id = _evaluate(base_url, token, str(part["id"]))
    glb = _fetch_mesh(base_url, token, mesh_id)
    ok(f"evaluated: volume {volume!r} mm^3, mesh {mesh_id[:19]}... ({len(glb)} B GLB)")

    assembly = _author_assembly(base_url, token, str(part["id"]))
    ok(f"authored assembly {assembly['id']} with instance {assembly['instance_id']}")

    drawing = _author_drawing(base_url, token, str(part["id"]))
    ok(f"authored drawing {drawing['id']} (sheet {drawing['sheet_id']} + a front view)")

    state = {
        "format": STATE_FORMAT,
        "email": email,
        "password": password,
        "part": {
            **part,
            "volume": volume,
            "mesh_glb_id": mesh_id,
            "glb_bytes": len(glb),
        },
        "assembly": assembly,
        "drawing": drawing,
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    print(f"\nseed: {len(steps)} checks passed; state written to {state_path}")


def _load_state(state_path: Path) -> dict[str, Any]:
    raw: Any = json.loads(state_path.read_text())
    state = _obj(raw, "state file")
    if state.get("format") != STATE_FORMAT:
        raise CheckFailed(
            f"state file {state_path} is not {STATE_FORMAT} "
            f"(got {state.get('format')!r})"
        )
    return state


def expect_empty(base_url: str, state_path: Path) -> None:
    """Assert this install does NOT have the seeded data (the A of the A/B).

    Run against the freshly-booted stack after the volumes were destroyed and
    before the restore. Without it, "the data is there after the restore" is
    only evidence that the data is there — it could have survived. With it, the
    drill has shown the same install answering both ways around one restore.
    """
    state = _load_state(state_path)
    login = request(
        base_url,
        "POST",
        "/api/v1/auth/login",
        payload={"email": state["email"], "password": state["password"]},
    )
    if login.status == 200:
        raise CheckFailed(
            f"{state['email']} can still log in on the FRESH stack — the volumes "
            "were not really destroyed, so a later successful login would prove "
            "nothing about the restore"
        )
    print(f"  ok  the fresh install rejects the seeded user (HTTP {login.status})")
    print("\nexpect-empty: this install is genuinely empty")


def verify(base_url: str, state_path: Path, *, cold_object_store: bool) -> None:
    """Assert every seeded document — and the GEOMETRY it rebuilds to — is back."""
    steps: list[str] = []

    def ok(message: str) -> None:
        steps.append(message)
        print(f"  ok  {message}", flush=True)

    state = _load_state(state_path)
    part = _obj(state["part"], "state.part")
    assembly = _obj(state["assembly"], "state.assembly")
    drawing = _obj(state["drawing"], "state.drawing")
    part_id = str(part["id"])

    # 1. The gateway's OWN database: the user row and its password hash. A
    #    restore that dropped it leaves every document unreachable.
    login = expect(
        request(
            base_url,
            "POST",
            "/api/v1/auth/login",
            payload={"email": state["email"], "password": state["password"]},
        ),
        200,
        "login as the pre-backup user",
    )
    token = str(login["access_token"])
    ok(f"logged in as {state['email']} (gateway identity rows restored)")

    # 2. The documents database: the part and its feature tree, verbatim.
    listed = expect(
        request(base_url, "GET", "/api/v1/parts", token=token), 200, "list parts"
    )
    names = {
        str(_obj(entry, "part")["id"]): str(_obj(entry, "part")["name"])
        for entry in _list(listed["parts"], "parts")
    }
    if names.get(part_id) != part["name"]:
        raise CheckFailed(
            f"part {part_id} ({part['name']!r}) is not in the restored "
            f"part list: {names}"
        )
    ok(f"part {part_id} is listed with its name {part['name']!r}")

    tree = expect(
        request(base_url, "GET", f"/api/v1/parts/{part_id}/features", token=token),
        200,
        "read the feature tree",
    )
    feature_ids = [
        str(_obj(entry, "feature")["id"])
        for entry in _list(tree["features"], "features")
    ]
    if feature_ids != [str(part["sketch_id"]), str(part["extrude_id"])]:
        raise CheckFailed(
            f"feature tree came back as {feature_ids}, expected "
            f"{[part['sketch_id'], part['extrude_id']]} in that order"
        )
    if int(tree["tree_version"]) != int(part["tree_version"]):
        raise CheckFailed(
            f"tree_version {tree['tree_version']} != pre-backup {part['tree_version']}"
        )
    ok(f"feature tree restored: {len(feature_ids)} features, ids and order identical")

    # 3. The object store really was destroyed — so step 4 cannot pass on a
    #    surviving cache. This is what makes the drill unable to fake itself.
    mesh_id = str(part["mesh_glb_id"])
    if cold_object_store:
        stale = request(
            base_url, "GET", f"/api/v1/geometry/meshes/{mesh_id}", token=token
        )
        if stale.status != 404:
            raise CheckFailed(
                f"the pre-backup mesh is still served (HTTP {stale.status}) — the "
                "object store was NOT destroyed, so re-deriving it proves nothing"
            )
        ok("pre-backup mesh is gone (404): the object store really was destroyed")

    # 4. THE assertion: rebuild the restored tree and demand the same solid.
    volume, rebuilt_mesh_id = _evaluate(base_url, token, part_id)
    if volume != float(part["volume"]):
        raise CheckFailed(
            f"re-evaluated volume {volume!r} mm^3 != pre-backup {part['volume']!r} mm^3"
        )
    if rebuilt_mesh_id != mesh_id:
        raise CheckFailed(
            f"re-evaluated mesh id {rebuilt_mesh_id} != pre-backup {mesh_id} — the "
            "restored tree does not rebuild to the same bytes"
        )
    ok(
        f"re-evaluated to the SAME solid: volume {volume!r} mm^3, "
        f"mesh {mesh_id[:19]}..."
    )

    glb = _fetch_mesh(base_url, token, mesh_id)
    if len(glb) != int(part["glb_bytes"]):
        raise CheckFailed(
            f"re-derived GLB is {len(glb)} B, pre-backup was {part['glb_bytes']} B"
        )
    ok(f"mesh re-derived into the fresh object store: {len(glb)} B, valid GLB")

    # 5. The other two document kinds, with their cross-document references.
    graph = expect(
        request(base_url, "GET", f"/api/v1/assemblies/{assembly['id']}", token=token),
        200,
        "read the assembly",
    )
    instances = [
        _obj(entry, "instance") for entry in _list(graph["instances"], "instances")
    ]
    match = [i for i in instances if str(i["id"]) == str(assembly["instance_id"])]
    if not match:
        raise CheckFailed(
            f"instance {assembly['instance_id']} missing from the restored assembly"
        )
    if str(match[0]["ref_document_id"]) != part_id:
        raise CheckFailed(
            f"restored instance points at {match[0]['ref_document_id']}, not {part_id}"
        )
    ok(
        f"assembly restored: instance {assembly['instance_id']} "
        "still references the part"
    )

    sheets_response = expect(
        request(base_url, "GET", f"/api/v1/drawings/{drawing['id']}", token=token),
        200,
        "read the drawing",
    )
    # Each entry of `sheets` is a sheet WITH its views/dimensions/annotations,
    # i.e. {"sheet": {...}, "views": [...], ...} — not a bare sheet.
    sheets = [
        _obj(entry, "sheet entry")
        for entry in _list(sheets_response["sheets"], "sheets")
    ]
    views = [
        _obj(view, "view")
        for entry in sheets
        if str(_obj(entry["sheet"], "sheet")["id"]) == str(drawing["sheet_id"])
        for view in _list(entry["views"], "views")
    ]
    matched = [view for view in views if str(view["id"]) == str(drawing["view_id"])]
    if not matched:
        raise CheckFailed(
            f"view {drawing['view_id']} missing from restored "
            f"sheet {drawing['sheet_id']}"
        )
    if str(matched[0]["ref_document_id"]) != part_id:
        raise CheckFailed(
            f"restored view points at {matched[0]['ref_document_id']}, not {part_id}"
        )
    ok(f"drawing restored: sheet {drawing['sheet_id']} still carries its front view")

    # 6. And the file an engineer takes to a shop still comes out.
    step = request(
        base_url, "POST", f"/api/v1/parts/{part_id}/export?format=step", token=token
    )
    if step.status != 200 or not step.body.startswith(b"ISO-10303-21"):
        raise CheckFailed(
            f"STEP export after restore: HTTP {step.status}, {step.text(80)!r}"
        )
    ok(f"exported STEP from the restored part: {len(step.body)} bytes")

    print(f"\nverify: {len(steps)} checks passed against {base_url}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("leg", choices=("seed", "expect-empty", "verify"))
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="published gateway origin (default: %(default)s)",
    )
    parser.add_argument("--state-out", help="where `seed` writes its state file")
    parser.add_argument("--state-in", help="the state file `verify` reads")
    parser.add_argument(
        "--assert-cold-object-store",
        action="store_true",
        help="demand the pre-backup mesh is a 404 before re-evaluating "
        "(proves the destroy step really destroyed the object store)",
    )
    args = parser.parse_args()
    base_url = str(args.base_url).rstrip("/")

    try:
        if args.leg == "seed":
            if not args.state_out:
                parser.error("seed needs --state-out")
            print(f"seed: driving {base_url} (gateway only, as a browser would)")
            seed(base_url, Path(str(args.state_out)))
        elif args.leg == "expect-empty":
            if not args.state_in:
                parser.error("expect-empty needs --state-in")
            print(f"expect-empty: probing {base_url} for the seeded user")
            expect_empty(base_url, Path(str(args.state_in)))
        else:
            if not args.state_in:
                parser.error("verify needs --state-in")
            print(f"verify: driving {base_url} against {args.state_in}")
            verify(
                base_url,
                Path(str(args.state_in)),
                cold_object_store=bool(args.assert_cold_object_store),
            )
    except CheckFailed as exc:
        print(f"\n{args.leg}: FAILED — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
