/**
 * The twisted prism's manifest as the gateway serves it
 * (packages/loft-plugins `MANIFEST_V1`), trimmed to the inputs the web tests
 * drive: the PLUGIN-UI unit tests' one fixture.
 */
import type { PluginManifest } from "../api/plugins";

export const TWISTED_PRISM: PluginManifest = {
  id: "loft.twisted_prism",
  version: "1.0.0",
  title: "Twisted prism",
  description: "A profile carried straight along its normal while it turns.",
  group: "build",
  latest: true,
  inputs: [
    { kind: "profile", name: "profile", label: "Profile" },
    {
      kind: "length",
      name: "distance_mm",
      label: "Distance",
      unit: "mm",
      default: 10,
      minimum: 0,
      exclusive_minimum: true,
    },
    {
      kind: "angle",
      name: "twist_angle_deg",
      label: "Twist angle",
      unit: "deg",
      default: 30,
      minimum: -3600,
      maximum: 3600,
      exclusive_minimum: false,
    },
    {
      kind: "choice",
      name: "operation",
      label: "Operation",
      default: "add",
      options: [
        { value: "add", label: "Join" },
        { value: "cut", label: "Cut" },
      ],
    },
  ],
  members: [
    { role: "path", title: "Path" },
    { role: "sweep", title: "Twisted sweep" },
  ],
};
