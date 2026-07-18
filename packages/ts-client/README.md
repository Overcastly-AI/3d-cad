# @loft/ts-client

**Everything under `src/` is GENERATED — do not edit; run `just gen`.**

Typed TypeScript client for the Loft services, generated from
`packages/contracts/*.openapi.json` by `scripts/gen-ts-client.mjs`:

- `src/<service>/schema.ts` — types via [openapi-typescript](https://openapi-ts.dev)
- `src/<service>/index.ts` — thin fetch wrapper via
  [openapi-fetch](https://openapi-ts.dev/openapi-fetch/) (`create<Service>Client`)

Source-only workspace package (like `@loft/design`): no build step, consumers
import the `.ts` sources through per-service entry points:

```ts
import { createGatewayClient } from "@loft/ts-client/gateway";

const gateway = createGatewayClient({ baseUrl: "/" });
```

Strict-TS validity of the generated output is enforced by
`pnpm -r typecheck` (this package's `tsc --noEmit`). Drift against the
committed contracts is enforced by `just gen-check` in CI.

Hand-written plumbing (this file, `package.json`, `tsconfig.json`) is the
only thing edited by humans/agents here.
