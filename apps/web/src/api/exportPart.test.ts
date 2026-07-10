import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { exportBox, parseContentDispositionFilename } from "./exportPart";

describe("parseContentDispositionFilename", () => {
  it("parses the quoted form the gateway sends", () => {
    expect(
      parseContentDispositionFilename(
        'attachment; filename="box.step"',
        "fallback.step",
      ),
    ).toBe("box.step");
  });

  it("parses a bare (unquoted) filename", () => {
    expect(
      parseContentDispositionFilename(
        "attachment; filename=box.stl; size=684",
        "fallback.stl",
      ),
    ).toBe("box.stl");
  });

  it("is case-insensitive and tolerates spacing", () => {
    expect(
      parseContentDispositionFilename(
        'ATTACHMENT; FILENAME = "box.step"',
        "fallback.step",
      ),
    ).toBe("box.step");
  });

  it("falls back when the header is missing or has no filename", () => {
    expect(parseContentDispositionFilename(null, "box.step")).toBe("box.step");
    expect(parseContentDispositionFilename("inline", "box.step")).toBe(
      "box.step",
    );
    expect(
      parseContentDispositionFilename('attachment; filename=""', "box.step"),
    ).toBe("box.step");
  });

  it("does not misread the RFC 5987 filename* form as a filename", () => {
    expect(
      parseContentDispositionFilename(
        "attachment; filename*=UTF-8''weird%20name.step",
        "box.step",
      ),
    ).toBe("box.step");
  });

  it("strips path segments a hostile header might smuggle in", () => {
    expect(
      parseContentDispositionFilename(
        'attachment; filename="../../etc/passwd"',
        "box.step",
      ),
    ).toBe("passwd");
    expect(
      parseContentDispositionFilename(
        'attachment; filename="C:\\parts\\box.stl"',
        "box.stl",
      ),
    ).toBe("box.stl");
  });
});

const PARAMS = { x: 10, y: 20, z: 30 };

/** Typed client whose transport is a canned response — no network. */
function clientReturning(response: Response) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: () => Promise.resolve(response),
  });
}

describe("exportBox", () => {
  it("returns the file blob and the Content-Disposition filename", async () => {
    const client = clientReturning(
      new Response("ISO-10303-21;\nHEADER;", {
        status: 200,
        headers: {
          "Content-Type": "model/step",
          "Content-Disposition": 'attachment; filename="box.step"',
        },
      }),
    );
    const file = await exportBox("step", PARAMS, client);
    expect(file.filename).toBe("box.step");
    expect(await file.blob.text()).toBe("ISO-10303-21;\nHEADER;");
  });

  it("falls back to box.<format> when the header is absent", async () => {
    const client = clientReturning(
      new Response(new Uint8Array([0, 1, 2]), {
        status: 200,
        headers: { "Content-Type": "model/stl" },
      }),
    );
    const file = await exportBox("stl", PARAMS, client);
    expect(file.filename).toBe("box.stl");
    expect(file.blob.size).toBe(3);
  });

  it("throws a labelled error when the gateway rejects the export", async () => {
    const client = clientReturning(
      new Response(
        JSON.stringify({ error: { code: "upstream_unavailable" } }),
        {
          status: 502,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    await expect(exportBox("step", PARAMS, client)).rejects.toThrow(
      /rejected the STEP export/,
    );
  });
});
