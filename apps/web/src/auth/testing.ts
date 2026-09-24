/**
 * Test helpers for the auth modules. Only `*.test.ts` files import this;
 * nothing in the app does, so it never reaches the bundle.
 */

function base64url(value: object): string {
  return btoa(JSON.stringify(value))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/** An unsigned JWT-shaped token with the given claims (scheduling only). */
export function fakeJwt(claims: object): string {
  return `${base64url({ alg: "HS256", typ: "JWT" })}.${base64url(claims)}.sig`;
}
