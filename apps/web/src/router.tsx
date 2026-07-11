import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router";

import { AuthedLayout } from "./routes/AuthedLayout";
import { ModelerPage } from "./routes/ModelerPage";
import { PartPage } from "./routes/PartPage";
import { PartsPage } from "./routes/PartsPage";
import { SignInPage } from "./routes/SignInPage";

const rootRoute = createRootRoute({
  component: Outlet,
});

const signInRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sign-in",
  component: SignInPage,
});

/** Everything below requires a session (see AuthedLayout). */
const authedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "authed",
  component: AuthedLayout,
});

/** The landing surface after sign-in: the parts register (create/open/delete). */
const indexRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/",
  component: PartsPage,
});

/**
 * The tessellation demo ("first light") — the OCCT box round-trip that proved
 * the viewport pipeline. Kept reachable off the parts home for pipeline smoke.
 */
const firstLightRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/first-light",
  component: ModelerPage,
});

/** Part workspace: feature tree + viewport + sketch mode. */
export const partRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/parts/$partId",
  component: PartPage,
});

const routeTree = rootRoute.addChildren([
  signInRoute,
  authedRoute.addChildren([indexRoute, firstLightRoute, partRoute]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
