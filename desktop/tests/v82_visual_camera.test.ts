import { describe, expect, it } from "vitest";
import { OrbitCamera, computeHeavyAtomCanonicalR } from "../src/engine/camera";
import {
  BOHR_TO_ANGSTROM,
  HARTREE_TO_KCAL_MOL,
  buildEspSurfaceMesh,
  buildOrbitalSurfaceMeshes,
  mapScalarToColor,
  parseGaussianCube,
} from "../src/engine/cubeIsosurface";

function makeSyntheticCube(nx = 9, ny = 9, nz = 9, mode: "mo" | "dens" | "esp" = "mo"): string {
  const stepBohr = 1.0;
  const originBohr = -4.0;
  const lines: string[] = [
    "MolForge synthetic test cube",
    "Generated inside vitest",
    `    2 ${originBohr.toFixed(6)} ${originBohr.toFixed(6)} ${originBohr.toFixed(6)}`,
    `${nx.toString().padStart(5)} ${stepBohr.toFixed(6)} 0.000000 0.000000`,
    `${ny.toString().padStart(5)} 0.000000 ${stepBohr.toFixed(6)} 0.000000`,
    `${nz.toString().padStart(5)} 0.000000 0.000000 ${stepBohr.toFixed(6)}`,
    "    6 6.000000 -1.000000 0.000000 0.000000",
    "    6 6.000000  1.000000 0.000000 0.000000",
  ];
  const vals: string[] = [];
  for (let i = 0; i < nx; i++) {
    const x = (originBohr + i * stepBohr) * BOHR_TO_ANGSTROM;
    for (let j = 0; j < ny; j++) {
      const y = (originBohr + j * stepBohr) * BOHR_TO_ANGSTROM;
      for (let k = 0; k < nz; k++) {
        const z = (originBohr + k * stepBohr) * BOHR_TO_ANGSTROM;
        const r2 = x * x + y * y + z * z;
        let v = 0;
        if (mode === "mo") {
          v = 0.08 * x * Math.exp(-0.28 * r2);
        } else if (mode === "dens") {
          v = 0.05 * Math.exp(-0.4 * r2);
        } else {
          v = -0.042 + ((x + 2.2) / 4.4) * (0.028 - -0.042);
        }
        vals.push(v.toExponential(5));
        if (vals.length === 6) {
          lines.push(vals.join(" "));
          vals.length = 0;
        }
      }
    }
  }
  if (vals.length > 0) lines.push(vals.join(" "));
  return lines.join("\n");
}

describe("P0 Camera Core-First & 4 Scientific Presets", () => {
  it("computes right-handed canonical frame and fits molecule within 88% ortho viewport", () => {
    // Elongated planar ribbon tilted in XYZ
    const pts = [
      [-4, -1, 0.2],
      [-2, -0.5, 0.1],
      [0, 0, 0],
      [2, 0.5, -0.1],
      [4, 1, -0.2],
      [0, 1.5, 0.4],
    ];
    const coords = new Float32Array(pts.flat());
    const zArr = new Uint8Array(pts.length).fill(6);

    const rCan = computeHeavyAtomCanonicalR(coords, pts.length, zArr);
    // Determinant of orthonormal R_can must be +1 (SO(3), no mirror)
    const [a, b, c] = rCan;
    const det =
      a[0] * (b[1] * c[2] - b[2] * c[1]) -
      a[1] * (b[0] * c[2] - b[2] * c[0]) +
      a[2] * (b[0] * c[1] - b[1] * c[0]);
    expect(det).toBeCloseTo(1, 5);

    const cam = new OrbitCamera();
    for (const preset of [
      "vertical_front",
      "horizontal_front",
      "side_edge",
      "paper_oblique",
    ] as const) {
      cam.applyScientificPreset(preset, coords, pts.length, 1200, 900, rCan, zArr, undefined, 0.88);
      expect(cam.orthographic).toBe(true);
      for (let i = 0; i < pts.length; i++) {
        const sp = cam.projectWorldToScreen(
          [coords[i * 3], coords[i * 3 + 1], coords[i * 3 + 2]],
          1200,
          900
        );
        expect(sp.visible).toBe(true);
        expect(sp.x).toBeGreaterThanOrEqual(20);
        expect(sp.x).toBeLessThanOrEqual(1180);
        expect(sp.y).toBeGreaterThanOrEqual(20);
        expect(sp.y).toBeLessThanOrEqual(880);
      }
    }
  });
});

describe("P1 Cube Parser, Marching Tetrahedra & BWR Dual-Unit Mapping", () => {
  it("parses .cub grids and extracts both MO lobes & BWR-colored ESP surface", () => {
    const moCube = parseGaussianCube(makeSyntheticCube(9, 9, 9, "mo"));
    expect(moCube.dims).toEqual([9, 9, 9]);
    const lobes = buildOrbitalSurfaceMeshes(moCube, 0.02, 0.78);
    expect(lobes.length).toBe(2);
    expect(lobes[0].vertexCount).toBeGreaterThan(20);
    expect(lobes[1].vertexCount).toBeGreaterThan(20);

    const densCube = parseGaussianCube(makeSyntheticCube(9, 9, 9, "dens"));
    const espCube = parseGaussianCube(makeSyntheticCube(9, 9, 9, "esp"));
    const espSurf = buildEspSurfaceMesh(densCube, espCube, 0.005, -0.042, 0.028, "BWR", 0.72);
    expect(espSurf.vertexCount).toBeGreaterThan(30);
    // Stride is 10 floats: px,py,pz, nx,ny,nz, r,g,b,a
    expect(espSurf.vertices.length).toBe(espSurf.vertexCount * 10);
  });

  it("maps asymmetric -0.042..+0.028 BWR midpoint cleanly to pure white and preserves a.u.<->kcal/mol", () => {
    const [rMin, gMin, bMin] = mapScalarToColor(-0.042, -0.042, 0.028, "BWR");
    expect(bMin).toBeCloseTo(1.0, 5);
    expect(rMin).toBeCloseTo(0.1, 5);
    expect(gMin).toBeCloseTo(0.1, 5);

    // Midpoint = -0.007 a.u. -> exact pure white (1, 1, 1)
    const [rMid, gMid, bMid] = mapScalarToColor(-0.007, -0.042, 0.028, "BWR");
    expect(rMid).toBeCloseTo(1.0, 5);
    expect(gMid).toBeCloseTo(1.0, 5);
    expect(bMid).toBeCloseTo(1.0, 5);

    const [rMax, gMax, bMax] = mapScalarToColor(0.028, -0.042, 0.028, "BWR");
    expect(rMax).toBeCloseTo(1.0, 5);
    expect(gMax).toBeCloseTo(0.1, 5);
    expect(bMax).toBeCloseTo(0.1, 5);

    expect(0.01 * HARTREE_TO_KCAL_MOL).toBeCloseTo(6.27509, 4);
  });
});
