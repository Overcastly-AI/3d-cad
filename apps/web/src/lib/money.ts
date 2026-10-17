/**
 * Money at the display boundary (CUT-LIST-PRICES). The wire carries integer
 * cents (RESEARCH §27) and the UI never does float arithmetic on them: a value
 * is split into whole units and cents as BigInts, Intl formats the whole units
 * with the currency's symbol and grouping, and the cents are spliced in as the
 * digits they are. Parsing goes the other way on the typed digits, so "19.98"
 * is 1998 exactly, never 1997.9999.
 */

const formats = new Map<string, Intl.NumberFormat>();

function currencyFormat(currency: string): Intl.NumberFormat {
  let format = formats.get(currency);
  if (format === undefined) {
    format = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    formats.set(currency, format);
  }
  return format;
}

function split(cents: number): {
  negative: boolean;
  whole: bigint;
  fraction: string;
} {
  if (!Number.isSafeInteger(cents)) {
    throw new RangeError(`Money must be integer cents, got ${cents}.`);
  }
  const value = BigInt(cents);
  const negative = value < 0n;
  const magnitude = negative ? -value : value;
  return {
    negative,
    whole: magnitude / 100n,
    fraction: (magnitude % 100n).toString().padStart(2, "0"),
  };
}

/** Integer cents as "$1,234.56" in `currency` (USD, the only book currency). */
export function formatMoney(cents: number, currency = "USD"): string {
  const { negative, whole, fraction } = split(cents);
  const parts = currencyFormat(currency).formatToParts(
    negative ? -whole : whole,
  );
  // -0n is 0n: a negative amount under a dollar would lose its sign.
  const signed =
    negative && whole === 0n
      ? [{ type: "minusSign", value: "-" }, ...parts]
      : parts;
  return signed
    .map((part) => (part.type === "fraction" ? fraction : part.value))
    .join("");
}

/** Integer cents as the plain decimal a field edits ("19.98", "1.45"). */
export function centsToDecimal(cents: number): string {
  const { negative, whole, fraction } = split(cents);
  return `${negative ? "-" : ""}${whole}.${fraction}`;
}

/**
 * A typed price as integer cents, or null when it is not one: digits with at
 * most two decimals, an optional leading "$" and thousands commas. Negative
 * prices are not prices.
 */
export function parseMoney(text: string): number | null {
  const match = /^\$?\s*(\d{1,3}(?:,\d{3})+|\d*)(?:\.(\d{0,2}))?$/.exec(
    text.trim(),
  );
  if (match === null) return null;
  const whole = (match[1] ?? "").replaceAll(",", "");
  const fraction = match[2] ?? "";
  if (whole === "" && fraction === "") return null;
  const cents =
    BigInt(whole === "" ? "0" : whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (cents > BigInt(Number.MAX_SAFE_INTEGER)) return null;
  return Number(cents);
}
