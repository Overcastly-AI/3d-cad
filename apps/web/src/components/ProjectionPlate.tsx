import { sketch } from "@loft/design";

/**
 * THE PROJECTION PLATE — the sign-in sheet's signature element (SIGNIN-1,
 * frontend-design pass 2026-08-26).
 *
 * The sign-in screen's old thesis was "an un-issued drawing sheet": nothing has
 * been drawn yet, so the sheet is blank and the auth form sits where a title
 * block sits — the bottom-right corner. The idea is right and the execution
 * produced the defect the audit filed four times: the "sheet" was the browser
 * WINDOW, which has no edges, so the title block was not in a corner of an
 * object, it was 82 % of the way across 94.8 % emptiness. A blank sheet is only
 * legible as a blank sheet when you can see the sheet.
 *
 * So the sheet became a bounded object, and this is what is drawn on it: a
 * third-angle orthographic plate of a machined angle bracket — top, front and
 * right-side views plus an isometric, with centrelines, hidden edges and two
 * driving dimensions. It is the most characteristic artefact in this product's
 * world and it is the thing the product MAKES, which is what the design skill
 * asks a hero to be. Nobody's sign-in page looks like this.
 *
 * THREE CONSTRAINTS IT DELIBERATELY RESPECTS:
 *
 *  - NO NEW INK. Every stroke reads a `sketch.*` token — the same palette the
 *    real sketcher scribes with. Not the `drawing.*` (paper/graphite) palette:
 *    tokens.ts states that the paper inversion is "spent boldly here and nowhere
 *    else", i.e. on the drawings surface, and spending it a second time on the
 *    sign-in would both break that claim and put a sheet of white paper in front
 *    of an app that is blued steel everywhere else. Before you sign in there is
 *    no part and no drawing — there is a scribe on the bench. This is that.
 *  - NO MOTION. A draw-on animation was the obvious next idea and is exactly the
 *    "scattered effects" the design skill warns reads as generated. The plate is
 *    still, so there is no `prefers-reduced-motion` branch to get wrong.
 *  - NO INTERACTION. It is `aria-hidden`: it says what the product is, it is not
 *    a control, and a screen-reader user gets the same information from the
 *    title strip's text. Nothing here is a fake affordance.
 *
 * The geometry is a real, consistent solid, not four drawings that merely look
 * like each other — the views are generated from ONE set of millimetre
 * dimensions below, so they cannot disagree about the part. Getting that wrong
 * on the front page of a CAD tool is the kind of detail its audience reads
 * instantly.
 */

// ── The part, in millimetres. One source; every view derives from it. ────────
/** Base plate: X 0..W, Y 0..D, Z 0..T. */
const BASE_W = 80;
const BASE_D = 50;
const BASE_T = 8;
/** Vertical web, rising from the plate's back edge (Y = 0). */
const WEB_X0 = 15;
const WEB_X1 = 65;
const WEB_T = 8;
const WEB_H = 40;
/** Two through-holes in the plate. */
const HOLE_R = 5;
const HOLE_Y = 34;
const HOLE_X = [20, 60];
/** One through-hole in the web. */
const WEB_HOLE_R = 6;
const WEB_HOLE_X = 40;
const WEB_HOLE_Z = 26;

// ── Stroke weights, in plate units (the viewBox is millimetres). ─────────────
const W_VISIBLE = 0.6;
const W_HIDDEN = 0.35;
const W_CENTRE = 0.3;
const W_DIM = 0.3;
const TEXT = 5;

// ── Sheet layout. Third angle: TOP above FRONT, RIGHT-SIDE beside it. ────────
/**
 * MARGIN is asymmetric because the sheet's contents are: the front view carries
 * a vertical dimension outside its left edge and a horizontal one under it, and
 * a symmetric margin put the "48" witness line 1 mm off the sheet frame. The
 * left and bottom margins are the ones a dimension has to live in.
 */
const MARGIN = 14;
const MARGIN_L = 24;
const MARGIN_B = 26;
const GAP = 20;
/**
 * The isometric is scaled to 0.8 so the pictorial does not tower over the
 * orthographic views it belongs with — at 1:1 its 105 mm envelope is more than
 * twice the front view's height and the plate reads as a picture with three
 * small diagrams beside it, rather than as a drawing.
 */
const ISO_SCALE = 0.8;
const ISO_W = 112.6 * ISO_SCALE;
const ISO_H = 105 * ISO_SCALE;

const FRONT_H = BASE_T + WEB_H;
const ROW1_H = Math.max(BASE_D, ISO_H);
const ROW2_Y = MARGIN + ROW1_H + GAP;
const COL2_X = MARGIN_L + BASE_W + 30;
/** TOP is bottom-aligned in row 1 so it sits directly over FRONT. */
const TOP_Y = MARGIN + ROW1_H - BASE_D;

const PLATE_W = COL2_X + ISO_W + MARGIN;
const PLATE_H = ROW2_Y + FRONT_H + MARGIN_B;

/** Isometric projection of a millimetre point. +X down-right, +Y down-left, +Z up. */
function iso(x: number, y: number, z: number): [number, number] {
  return [(x - y) * 0.866 * ISO_SCALE, ((x + y) * 0.5 - z) * ISO_SCALE];
}

/**
 * A circle lying in the XY plane projects, under isometric, to an AXIS-ALIGNED
 * ellipse: substituting (r cos t, r sin t) gives r*sqrt(2)*cos30 in x and
 * r*sqrt(2)*sin30 in y, with no cross term. So it needs no rotation — which is
 * why the bores below are plain `<ellipse>` elements rather than transformed
 * circles.
 */
const ISO_ELLIPSE_RX = Math.SQRT2 * 0.866 * ISO_SCALE;
const ISO_ELLIPSE_RY = Math.SQRT2 * 0.5 * ISO_SCALE;

const CENTRE_DASH = "5 1.2 1 1.2";
const HIDDEN_DASH = `${sketch.constructionDashMm * 1.4} ${sketch.constructionGapMm}`;

export function ProjectionPlate({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox={`0 0 ${PLATE_W} ${PLATE_H}`}
      preserveAspectRatio="xMidYMid meet"
      fill="none"
      aria-hidden="true"
      data-testid="projection-plate"
    >
      <g transform={`translate(${MARGIN_L} ${TOP_Y})`}>
        <TopView />
        <ViewLabel x={0} y={BASE_D + 9} text="TOP" />
      </g>
      <g transform={`translate(${MARGIN_L} ${ROW2_Y})`}>
        <FrontView />
        {/* Below its own dimension line, not beside it: the label and the "80"
            witness shared a baseline in the first build and read as one string. */}
        <ViewLabel x={0} y={FRONT_H + 22} text="FRONT" />
      </g>
      <g transform={`translate(${COL2_X} ${ROW2_Y})`}>
        <RightView />
        <ViewLabel x={0} y={FRONT_H + 9} text="RIGHT SIDE" />
      </g>
      {/* The pictorial sits where a fourth quadrant is empty on a real sheet. */}
      <g
        transform={`translate(${COL2_X + 43.3 * ISO_SCALE} ${MARGIN + 40 * ISO_SCALE})`}
      >
        <IsoView />
      </g>
    </svg>
  );
}

/** Looking down: X right, the part's BACK edge at the top (third angle). */
function TopView() {
  return (
    <g>
      <rect
        x={0}
        y={0}
        width={BASE_W}
        height={BASE_D}
        stroke={sketch.scribe}
        strokeWidth={W_VISIBLE}
      />
      {/* The web's footprint against the back edge. */}
      <rect
        x={WEB_X0}
        y={0}
        width={WEB_X1 - WEB_X0}
        height={WEB_T}
        stroke={sketch.scribe}
        strokeWidth={W_VISIBLE}
      />
      {HOLE_X.map((x) => (
        <g key={x}>
          <circle
            cx={x}
            cy={HOLE_Y}
            r={HOLE_R}
            stroke={sketch.scribe}
            strokeWidth={W_VISIBLE}
          />
          <Centre cx={x} cy={HOLE_Y} r={HOLE_R + 3} />
        </g>
      ))}
      {/* The web bore's axis, carried through as a centreline — the convention
          that ties one view to another. */}
      <line
        x1={WEB_HOLE_X}
        y1={-4}
        x2={WEB_HOLE_X}
        y2={WEB_T + 4}
        stroke={sketch.constructionInk}
        strokeWidth={W_CENTRE}
        strokeDasharray={CENTRE_DASH}
      />
    </g>
  );
}

/** Looking along -Y: X right, Z up (drawn with the plate's underside at y = H). */
function FrontView() {
  const baseTop = WEB_H;
  return (
    <g>
      {/* Silhouette: plate along the bottom, web tower above it. */}
      <path
        d={`M 0 ${baseTop} H ${WEB_X0} V 0 H ${WEB_X1} V ${baseTop} H ${BASE_W} V ${FRONT_H} H 0 Z`}
        stroke={sketch.scribe}
        strokeWidth={W_VISIBLE}
      />
      {/* Where the web meets the plate — a real edge, so a real line. */}
      <line
        x1={WEB_X0}
        y1={baseTop}
        x2={WEB_X1}
        y2={baseTop}
        stroke={sketch.scribe}
        strokeWidth={W_VISIBLE}
      />
      <circle
        cx={WEB_HOLE_X}
        cy={WEB_H - WEB_HOLE_Z}
        r={WEB_HOLE_R}
        stroke={sketch.scribe}
        strokeWidth={W_VISIBLE}
      />
      <Centre cx={WEB_HOLE_X} cy={WEB_H - WEB_HOLE_Z} r={WEB_HOLE_R + 4} />
      {/* The plate's bores, occluded from the front: hidden edges. */}
      {HOLE_X.flatMap((x) => [x - HOLE_R, x + HOLE_R]).map((x) => (
        <line
          key={x}
          x1={x}
          y1={baseTop}
          x2={x}
          y2={FRONT_H}
          stroke={sketch.constructionInk}
          strokeWidth={W_HIDDEN}
          strokeDasharray={HIDDEN_DASH}
        />
      ))}
      <DimH y={FRONT_H + 11} x1={0} x2={BASE_W} label="80" />
      <DimV x={-14} y1={0} y2={FRONT_H} label="48" />
    </g>
  );
}

/**
 * Looking along -X, Z up.
 *
 * THE HORIZONTAL AXIS IS MIRRORED, and that mirror is the whole difference
 * between third angle and first angle. Unfolding the glass box puts the edge
 * NEAREST the front view against the part's FRONT face, so in a third-angle
 * right-side view the part's front (Y = D) is on the LEFT and its back (Y = 0)
 * on the right — which is why the web, which stands on the back edge, draws at
 * the RIGHT here and at the TOP of the top view. Drawn the intuitive way round
 * ("Y increases to the right, because that is what I see standing there") this
 * view is a correct FIRST-angle projection on a sheet whose symbol says third,
 * which is exactly the sort of quiet wrongness a mechanical engineer reads in
 * about a second and cannot unsee.
 */
function RightView() {
  /** Part-space Y to view-space x: the third-angle mirror, in one place. */
  const vx = (y: number) => BASE_D - y;
  return (
    <g>
      <path
        d={`M ${vx(0)} ${FRONT_H} H ${vx(BASE_D)} V ${WEB_H} H ${vx(WEB_T)} V 0 H ${vx(0)} Z`}
        stroke={sketch.scribe}
        strokeWidth={W_VISIBLE}
      />
      {/* The plate's bores, seen edge-on. */}
      {[HOLE_Y - HOLE_R, HOLE_Y + HOLE_R].map((y) => (
        <line
          key={y}
          x1={vx(y)}
          y1={WEB_H}
          x2={vx(y)}
          y2={FRONT_H}
          stroke={sketch.constructionInk}
          strokeWidth={W_HIDDEN}
          strokeDasharray={HIDDEN_DASH}
        />
      ))}
      {/* The web's bore, seen edge-on. */}
      {[WEB_HOLE_Z - WEB_HOLE_R, WEB_HOLE_Z + WEB_HOLE_R].map((z) => (
        <line
          key={z}
          x1={vx(0)}
          y1={WEB_H - z}
          x2={vx(WEB_T)}
          y2={WEB_H - z}
          stroke={sketch.constructionInk}
          strokeWidth={W_HIDDEN}
          strokeDasharray={HIDDEN_DASH}
        />
      ))}
      <line
        x1={vx(0) + 4}
        y1={WEB_H - WEB_HOLE_Z}
        x2={vx(WEB_T) - 4}
        y2={WEB_H - WEB_HOLE_Z}
        stroke={sketch.constructionInk}
        strokeWidth={W_CENTRE}
        strokeDasharray={CENTRE_DASH}
      />
    </g>
  );
}

/**
 * The pictorial. Occlusion is done by PAINTING, not by an edge-visibility
 * calculation: the three faces of each box that face the (1,1,1) viewpoint are
 * filled with the ground colour back-to-front, so the web correctly covers the
 * part of the plate it stands on, and no hidden edge has to be reasoned about.
 */
function IsoView() {
  const face = (points: [number, number, number][]) =>
    points.map(([x, y, z]) => iso(x, y, z).join(",")).join(" ");

  const faces: [number, number, number][][] = [
    // Plate: top, then the two faces toward the viewer.
    [
      [0, 0, BASE_T],
      [BASE_W, 0, BASE_T],
      [BASE_W, BASE_D, BASE_T],
      [0, BASE_D, BASE_T],
    ],
    [
      [BASE_W, 0, BASE_T],
      [BASE_W, BASE_D, BASE_T],
      [BASE_W, BASE_D, 0],
      [BASE_W, 0, 0],
    ],
    [
      [0, BASE_D, BASE_T],
      [BASE_W, BASE_D, BASE_T],
      [BASE_W, BASE_D, 0],
      [0, BASE_D, 0],
    ],
    // Web, painted after the plate so it occludes the plate's top face.
    [
      [WEB_X0, 0, WEB_H],
      [WEB_X1, 0, WEB_H],
      [WEB_X1, WEB_T, WEB_H],
      [WEB_X0, WEB_T, WEB_H],
    ],
    [
      [WEB_X0, WEB_T, WEB_H],
      [WEB_X1, WEB_T, WEB_H],
      [WEB_X1, WEB_T, BASE_T],
      [WEB_X0, WEB_T, BASE_T],
    ],
    [
      [WEB_X1, 0, WEB_H],
      [WEB_X1, WEB_T, WEB_H],
      [WEB_X1, WEB_T, BASE_T],
      [WEB_X1, 0, BASE_T],
    ],
  ];

  return (
    <g>
      {faces.map((points, index) => (
        <polygon
          key={index}
          points={face(points)}
          fill={sketch.faceBluing}
          stroke={sketch.scribeSolved}
          strokeWidth={W_VISIBLE * 0.9}
          strokeLinejoin="round"
        />
      ))}
      {/* The plate's bores. A horizontal circle projects to an axis-aligned
          ellipse under isometric, so no rotation is needed. */}
      {HOLE_X.map((x) => {
        const [cx, cy] = iso(x, HOLE_Y, BASE_T);
        return (
          <ellipse
            key={x}
            cx={cx}
            cy={cy}
            rx={HOLE_R * ISO_ELLIPSE_RX}
            ry={HOLE_R * ISO_ELLIPSE_RY}
            stroke={sketch.scribeSolved}
            strokeWidth={W_VISIBLE * 0.9}
          />
        );
      })}
      {/*
        The web's bore. It lies in the XZ plane, whose projection is a ROTATED
        ellipse — unlike the horizontal ones above, the cross term does not
        vanish — so rather than solve for its axes it is drawn as the unit circle
        under the projection's own linear map: the matrix columns are just the
        images of (1,0) and (0,1), which is the projection evaluated twice.
        Deriving it this way means it cannot disagree with `iso()`.

        It matters that it is here at all: the front and right views both show
        this hole, so an isometric without it would be a fourth view of a
        DIFFERENT part. Three views agreeing and one not is the specific error a
        drawing is checked for.
      */}
      <circle
        cx={0}
        cy={0}
        r={1}
        transform={`matrix(${WEB_HOLE_R * 0.866 * ISO_SCALE} ${
          WEB_HOLE_R * 0.5 * ISO_SCALE
        } 0 ${-WEB_HOLE_R * ISO_SCALE} ${iso(
          WEB_HOLE_X,
          WEB_T,
          WEB_HOLE_Z,
        ).join(" ")})`}
        stroke={sketch.scribeSolved}
        strokeWidth={(W_VISIBLE * 0.9) / (WEB_HOLE_R * ISO_SCALE)}
        vectorEffect="none"
      />
    </g>
  );
}

/** The dash-dot cross a bore's axis is drawn with. */
function Centre({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g
      stroke={sketch.constructionInk}
      strokeWidth={W_CENTRE}
      strokeDasharray={CENTRE_DASH}
    >
      <line x1={cx - r} y1={cy} x2={cx + r} y2={cy} />
      <line x1={cx} y1={cy - r} x2={cx} y2={cy + r} />
    </g>
  );
}

/**
 * A driving dimension, in the brass every dimension in this product is drawn
 * in (`sketch.glyphDimension`) — the one accent on the plate, and it is the
 * accent because a dimension is the parametric handle, which is the whole
 * argument of the product.
 */
function DimH({
  y,
  x1,
  x2,
  label,
}: {
  y: number;
  x1: number;
  x2: number;
  label: string;
}) {
  return (
    <g stroke={sketch.glyphDimension} strokeWidth={W_DIM}>
      <line x1={x1} y1={y} x2={x2} y2={y} />
      <line x1={x1} y1={y - 3} x2={x1} y2={y + 3} />
      <line x1={x2} y1={y - 3} x2={x2} y2={y + 3} />
      <text
        className="font-data"
        x={(x1 + x2) / 2}
        y={y - 2.5}
        fontSize={TEXT}
        textAnchor="middle"
        fill={sketch.glyphDimension}
        stroke="none"
      >
        {label}
      </text>
    </g>
  );
}

function DimV({
  x,
  y1,
  y2,
  label,
}: {
  x: number;
  y1: number;
  y2: number;
  label: string;
}) {
  return (
    <g stroke={sketch.glyphDimension} strokeWidth={W_DIM}>
      <line x1={x} y1={y1} x2={x} y2={y2} />
      <line x1={x - 3} y1={y1} x2={x + 3} y2={y1} />
      <line x1={x - 3} y1={y2} x2={x + 3} y2={y2} />
      <text
        className="font-data"
        x={x - 2.5}
        y={(y1 + y2) / 2}
        fontSize={TEXT}
        textAnchor="middle"
        fill={sketch.glyphDimension}
        stroke="none"
        transform={`rotate(-90 ${x - 2.5} ${(y1 + y2) / 2})`}
      >
        {label}
      </text>
    </g>
  );
}

function ViewLabel({ x, y, text }: { x: number; y: number; text: string }) {
  return (
    <text
      className="font-display"
      x={x}
      y={y}
      fontSize={TEXT * 0.78}
      letterSpacing={1.1}
      fill={sketch.constructionInk}
    >
      {text}
    </text>
  );
}

/**
 * THE THIRD-ANGLE SYMBOL — the truncated cone drawn in two views, which is how
 * a drawing states which projection convention it uses. It is the plate's one
 * connoisseur's detail: an engineer reads it without being told, and no
 * templated sign-in has ever carried one. Exported for the sheet's title strip,
 * where a real drawing prints it.
 */
export function ThirdAngleSymbol({ className }: { className?: string }) {
  const ink = sketch.constructionInk;
  return (
    <svg
      className={className}
      viewBox="0 0 34 14"
      fill="none"
      aria-hidden="true"
      data-testid="third-angle-symbol"
    >
      {/* The cone's end view: two concentric circles. */}
      <circle cx="7" cy="7" r="6" stroke={ink} strokeWidth="0.7" />
      <circle cx="7" cy="7" r="3.2" stroke={ink} strokeWidth="0.7" />
      {/* The cone in section, its taper opening away from the end view. */}
      <path
        d="M 18 1 L 33 3.8 L 33 10.2 L 18 13 Z"
        stroke={ink}
        strokeWidth="0.7"
      />
      <line
        x1="15"
        y1="7"
        x2="34"
        y2="7"
        stroke={ink}
        strokeWidth="0.4"
        strokeDasharray="3 0.9 0.7 0.9"
      />
    </svg>
  );
}
