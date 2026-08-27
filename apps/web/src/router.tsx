import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router";

import { AssembliesPage } from "./routes/AssembliesPage";
import { AssemblyPage } from "./routes/AssemblyPage";
import { AuthedLayout } from "./routes/AuthedLayout";
import { DrawingPage } from "./routes/DrawingPage";
import { DrawingsPage } from "./routes/DrawingsPage";
import { ModelerPage } from "./routes/ModelerPage";
import { PartPage } from "./routes/PartPage";
import { PartsPage } from "./routes/PartsPage";
import { SettingsPage } from "./routes/SettingsPage";
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

/** The assemblies register — sibling of the parts home. */
const assembliesRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/assemblies",
  component: AssembliesPage,
});

/** Assembly workspace: instance/mate tree + multi-instance viewport. */
export const assemblyRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/assemblies/$assemblyId",
  component: AssemblyPage,
});

/** The drawings register — sibling of the parts + assemblies homes. */
const drawingsRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/drawings",
  component: DrawingsPage,
});

/**
 * Drawing workspace: an engineering sheet + the standard views.
 *
 * `?source=<document id>` pre-selects the sheet's source in the setup band —
 * the hand-off another workspace's "Drawing" action uses, so the sheet opens
 * pointed at the document you were already looking at. Advisory only: the page
 * honours it just once, and only for a source that exists.
 */
export const drawingRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/drawings/$drawingId",
  component: DrawingPage,
  validateSearch: (
    search: Record<string, unknown>,
  ): { source?: string } | Record<string, never> =>
    typeof search.source === "string" && search.source.length > 0
      ? { source: search.source }
      : {},
});

/** Application preferences (#58) — a sibling of the registers, not a modal. */
const settingsRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/settings",
  component: SettingsPage,
});

const routeTree = rootRoute.addChildren([
  signInRoute,
  authedRoute.addChildren([
    indexRoute,
    firstLightRoute,
    partRoute,
    assembliesRoute,
    assemblyRoute,
    drawingsRoute,
    drawingRoute,
    settingsRoute,
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
