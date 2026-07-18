import { loftPreset } from "@loft/design/tailwind-preset";
import type { Config } from "tailwindcss";

export default {
  presets: [loftPreset],
  // Include the design package so primitive classes are generated.
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../../packages/design/src/**/*.{ts,tsx}",
  ],
} satisfies Config;
