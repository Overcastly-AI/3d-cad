import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router";

import { AuthedLayout } from "./routes/AuthedLayout";
import { ModelerPage } from "./routes/ModelerPage";
import { PartPage } from "./routes/PartPage";
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

const indexRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: "/",
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
  authedRoute.addChildren([indexRoute, partRoute]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
