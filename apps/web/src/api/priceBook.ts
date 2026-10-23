/**
 * Price-book data layer (PRICE-BOOK, RESEARCH §27): the caller's one book of
 * what they pay per stock piece, sheet, linear foot or board foot, in integer
 * cents. A `PUT` replaces the whole book. Every type comes from the generated
 * `@loft/ts-client`; the pricing itself is the gateway's, never redone here.
 *
 * PRICE-BOOK-VERSION: the book carries a `version` (its ETag). A save sends
 * the version its draft was read at as `If-Match`, and the gateway refuses it
 * with 412 when the book has been saved since: {@link PriceBookChangedError}.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeMessage } from "./envelope";

export type PriceBook = components["schemas"]["PriceBookResponse"];
export type PriceBookEntry = components["schemas"]["PriceBookEntry"];
export type PriceUnit = PriceBookEntry["unit"];
export type LumberProfile = components["schemas"]["LumberProfile"];
export type LumberProfileKey = LumberProfile["key"];
export type SheetGood = components["schemas"]["SheetGood"];
export type SheetGoodKey = SheetGood["key"];
export type SheetSize = components["schemas"]["SheetSize"];
export type SheetSizeKey = SheetSize["key"];
export type FoundationItem = components["schemas"]["FoundationItem"];
/** What an entry prices: lumber, a sheet product, a unit or a foundation item. */
export type PriceProfileKey = PriceBookEntry["profile"];

/**
 * The stock lengths an `each` price may be for (ft), shortest first. Mirrors
 * `loft_wire.lumber.STOCK_LENGTHS_FT`, which the API does not serve; the
 * gateway refuses any other length with a 422, so a drift fails loudly.
 */
export const STOCK_LENGTHS_FT: readonly number[] = [
  8, 10, 12, 14, 16, 18, 20, 22, 24,
];

/** How a unit reads in the dialog and the cut list. */
export const PRICE_UNIT_LABEL: Record<PriceUnit, string> = {
  each: "Each",
  linear_foot: "Per ft",
  board_foot: "Per BF",
  cubic_yard: "Per yd³",
};

/** Why a save was refused: the stored book is no longer the one drafted. */
export const BOOK_CHANGED =
  "The price book changed elsewhere (another tab or device) since you opened it. Reload it, then make your changes again.";

/** The gateway's 412: the book was saved since this draft's version. */
export class PriceBookChangedError extends Error {
  constructor() {
    super(BOOK_CHANGED);
    this.name = "PriceBookChangedError";
  }
}

/** The caller's book; an empty USD book (version 0) when they never saved one. */
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

/**
 * Replace the caller's whole book, if it is still at `version` (the version
 * the draft was read at). A book saved since is refused by the server and
 * this throws {@link PriceBookChangedError}; nothing is overwritten.
 */
export async function savePriceBook(
  entries: PriceBookEntry[],
  version: number,
  client: GatewayClient = gatewayClient,
): Promise<PriceBook> {
  const { data, error, response } = await client.PUT("/api/v1/price-book", {
    params: { header: { "If-Match": `"${version}"` } },
    body: { currency: "USD", entries },
  });
  if (error !== undefined) {
    if (response.status === 412) throw new PriceBookChangedError();
    throw new Error(
      envelopeMessage(error, "The price book could not be saved."),
    );
  }
  return data;
}
