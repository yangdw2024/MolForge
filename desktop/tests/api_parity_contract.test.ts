import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

describe("API Parity Contract Verification", () => {
  it("ensures every frontend endpoint in api.ts is implemented in molforge-server", () => {
    const apiTsPath = path.resolve(__dirname, "../src/services/api.ts");
    const mainRsPath = path.resolve(__dirname, "../../molforge-core/crates/molforge-server/src/main.rs");

    expect(fs.existsSync(apiTsPath)).toBe(true);
    expect(fs.existsSync(mainRsPath)).toBe(true);

    const apiTsContent = fs.readFileSync(apiTsPath, "utf-8");
    const mainRsContent = fs.readFileSync(mainRsPath, "utf-8");

    // Extract all "/api/..." string literals from api.ts
    const endpointRegex = /"(\/api\/[a-zA-Z0-9_/]+)"/g;
    const frontendEndpoints = new Set<string>();

    let match: RegExpExecArray | null;
    while ((match = endpointRegex.exec(apiTsContent)) !== null) {
      frontendEndpoints.add(match[1]);
    }

    expect(frontendEndpoints.size).toBeGreaterThan(25);

    const missingInBackend: string[] = [];
    for (const endpoint of frontendEndpoints) {
      // Endpoint must appear inside main.rs
      if (!mainRsContent.includes(`"${endpoint}"`)) {
        missingInBackend.push(endpoint);
      }
    }

    if (missingInBackend.length > 0) {
      console.error("Missing endpoints in Rust molforge-server:", missingInBackend);
    }

    expect(missingInBackend).toEqual([]);
  });

  it("ensures critical scientific routes (/api/ai/chat, clean_3d, insert_fragment, inspect_smiles, run_external) exist", () => {
    const mainRsPath = path.resolve(__dirname, "../../molforge-core/crates/molforge-server/src/main.rs");
    const mainRsContent = fs.readFileSync(mainRsPath, "utf-8");

    const criticalRoutes = [
      "/api/ai/chat",
      "/api/edit/clean_3d",
      "/api/edit/insert_fragment",
      "/api/library/inspect_smiles",
      "/api/qc/run_external",
      "/api/document",
      "/api/atoms",
      "/api/elements",
      "/api/fragments",
      "/api/qc/tight_binding",
      "/api/qc/run_calchem",
      "/api/qc/run_xtb",
    ];

    for (const route of criticalRoutes) {
      expect(mainRsContent).toContain(`"${route}"`);
    }
  });
});
