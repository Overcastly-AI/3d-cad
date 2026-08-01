# Viewport GLB fixtures

Real kernel output, not hand-built payloads — the face-partition contract
between `services/geometry/src/geometry/kernel/tessellate.py` and
`glbGeometry.ts` is only worth testing against bytes OCCT actually writes.

Both files describe the SAME two-body part (a notched 30x20x10 block and a
24x16x6 plate with a through slot, 40 mm apart): 20 B-rep faces, 52 triangles,
90 vertices, triangle counts per face `[2,2,4,4,2,4,2,2,2,2,2,8,2,2,2,2,2,2,2,2]`.

- `two-bodies-unfused.glb` — what `RWGltf_CafWriter` writes: one glTF primitive
  per B-rep face (20 primitives, 10 396 B). This is still the shipped encoding
  for triangle-dense parts (`FUSE_MAX_TRIANGLES_PER_FACE`), so it is a live
  path, not a legacy one.
- `two-bodies-fused.glb` — the same part after `tessellate.fuse_faces`: one
  primitive per mesh (2 primitives, 4 308 B), each carrying its per-face
  triangle counts in `extras.LOFT_face_triangles`.

`glbGeometry.test.ts` parses both and asserts they produce the SAME face
ordinals, the same buffers and the same lumps — that equality is what keeps
`on_face` datums, shell openings, hole placement and sketch-on-face pointing at
the face the user clicked.

Regenerate (from the repo root, after a kernel or OCCT change):

```python
import pathlib, tempfile
from build123d import Box, Compound, Pos, Unit
from build123d.exporters3d import export_gltf
from geometry.kernel import tessellate as T

notched = (Box(30, 20, 10) - Pos(12, 7, 4) * Box(10, 10, 10)).solid()
plate = (Box(24, 16, 6) - Pos(0, 0, 1) * Box(10, 6, 6)).solid()
shape = Compound(children=[notched, (Pos(0, 40, 0) * plate).solid()])
with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp) / "s.glb"
    export_gltf(shape, p, unit=Unit.MM, binary=True,
                linear_deflection=0.1, angular_deflection=T.ANGULAR_DEFLECTION)
    raw = p.read_bytes()
out = pathlib.Path("apps/web/src/viewport/__fixtures__")
(out / "two-bodies-unfused.glb").write_bytes(raw)
(out / "two-bodies-fused.glb").write_bytes(T.fuse_faces(raw))
```
