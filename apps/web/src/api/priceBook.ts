/**
 * Price-book data layer (PRICE-BOOK, RESEARCH §27): the caller's one book of
 * what they pay per stock piece, linear foot or board foot, in integer cents.
 * A `PUT` replaces the whole book. Every type comes from the generated
 * `@loft/ts-client`; the pricing itself is the gateway's, never redone here.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";

export type PriceBook = components["schemas"]["PriceBookResponse"];
export type PriceBookEntry = components["schemas"]["PriceBookEntry"];
export type PriceUnit = PriceBookEntry["unit"];
export type LumberProfile = components["schemas"]["LumberProfile"];
export type LumberProfileKey = LumberProfile["key"];

/**
 * The stock lengths an `each` price may be for (ft), shortest first. Mirrors
 * `loft_wire.lumber.STOCK_LENGTHS_FT`, which the API does not serve; the
 * gateway refuses any other length with a 422, so a drift fails loudly.
 */
export const STOCK_LENGTHS_FT: readonly number[] = [8, 10, 12, 14, 16, 20];

/** How a unit reads in the dialog and the cut list. */
export const PRICE_UNIT_LABEL: Record<PriceUnit, string> = {
  each: "Each",
  linear_foot: "Per ft",
  board_foot: "Per BF",
};

/** The caller's book; an empty USD book when they never saved one. */
export async function fetchPriceBook(
  client: GatewayClient = gatewayClient,
): Promise<PriceBook> {
  const { data, error } = await client.GET("/api/v1/price-book");
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The price book could not be loaded."),
    );
  }
  return data;
}

/** Replace the caller's whole book (the later of two saves wins whole). */
export async function savePriceBook(
  entries: PriceBookEntry[],
  client: GatewayClient = gatewayClient,
): Promise<PriceBook> {
  const { data, error } = await client.PUT("/api/v1/price-book", {
    body: { currency: "USD", entries },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "The price book could not be saved."),
    );
  }
  return data;
}
