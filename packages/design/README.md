# @loft/design

Loft's design system — the single source of truth for how the product looks,
in **both renderers**: the Tailwind preset styles the DOM, and the r3f
viewport reads the same TS token constants for scene colors (selection,
hover, grid, background). One palette, two renderers; no hex value exists
outside `src/tokens.ts`.

Source-only pnpm workspace package (no build step) — see `docs/RESEARCH.md`
§5 and the CLAUDE.md design mandate.

## Direction (frontend-design plan, 2026-07-10)

The machine shop, not a SaaS dashboard. The viewport is the hero; chrome is
quiet precision instrumentation.

- **Palette** — `carbide` gun-blued-steel ground (deliberately not
  near-black), `anvil` panel surfaces, `mist`/`gauge` text, one accent:
  `brass` (scribed line / DRO), `aluminum` model material. All text pairs
  verified ≥ 7:1 (WCAG AAA); control borders (`etch`) ≥ 3:1.
- **Type** — Hanken Grotesk (body/UI) + Fragment Mono (display eyebrows +
  data readouts), self-hosted via @fontsource.
- **Signature element** — the **title-block panel** (`Panel` /
  `PanelSection` / `PanelRow`): the inspector composed like an
  engineering-drawing title block — ruled cells, tracked eyebrow labels,
  tabular mono values. Boldness is spent here; everything else stays quiet.

## Entry points

| Import                        | Contents                                             |
| ----------------------------- | ---------------------------------------------------- |
| `@loft/design/tokens`         | Color / viewport / type / spacing / radius / motion  |
| `@loft/design/tailwind-preset`| Tailwind preset derived from the tokens              |
| `@loft/design/fonts`          | Self-hosted @fontsource CSS side-effect imports      |
| `@loft/design`                | Primitives: `Button`, `Panel(+Section/Row)`, `Toolbar`, `Chip`, `NumberField`, plus tokens re-export |

## Rules

- Never duplicate a hex value — extend `tokens.ts` instead.
- Fix the primitive, not the instance: app code never restyles raw elements.
- New primitives land on the second real use, not the first imagined one.
