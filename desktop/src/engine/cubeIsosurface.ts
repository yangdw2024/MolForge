// Gaussian .cub parser, trilinear ESP sampler, Marching Tetrahedra isosurface extractor,
// and absolute BWR / RWB / Viridis scalar color mapping (1 a.u. = 627.509474 kcal/mol).

export const BOHR_TO_ANGSTROM = 0.529177210903;
export const HARTREE_TO_KCAL_MOL = 627.5094740631;

export type SurfaceColormap = "BWR" | "RWB" | "Viridis";

export interface GaussianCubeData {
  comment1: string;
  comment2: string;
  dims: [number, number, number];
  originAngstrom: [number, number, number];
  axesAngstrom: [
    [number, number, number],
    [number, number, number],
    [number, number, number],
  ];
  atoms: Array<{ z: number; charge: number; posAngstrom: [number, number, number] }>;
  values: Float32Array;
  minVal: number;
  maxVal: number;
}

export interface SurfaceMeshData {
  name: string;
  /** Interleaved float32 per vertex: px,py,pz, nx,ny,nz, r,g,b,a (10 floats = 40 bytes). */
  vertices: Float32Array;
  vertexCount: number;
  worldPoints: Float32Array;
}

/** Parse standard Gaussian `.cub` / `.cube` volumetric scalar grid (Bohr -> Angstrom). */
export function parseGaussianCube(text: string): GaussianCubeData {
  const lines = text.split(/\r?\n/);
  if (lines.length < 7) {
    throw new Error("无效 .cub 文件：头部行数不足");
  }
  const comment1 = lines[0]?.trim() ?? "";
  const comment2 = lines[1]?.trim() ?? "";

  const headerParts = lines[2].trim().split(/\s+/);
  const rawNAtoms = parseInt(headerParts[0], 10);
  if (!Number.isFinite(rawNAtoms) || rawNAtoms === 0) {
    throw new Error(`无效 .cub 原子数: ${headerParts[0]}`);
  }
  const hasMoHeader = rawNAtoms < 0;
  const nAtoms = Math.abs(rawNAtoms);
  const originAngstrom: [number, number, number] = [
    parseFloat(headerParts[1]) * BOHR_TO_ANGSTROM,
    parseFloat(headerParts[2]) * BOHR_TO_ANGSTROM,
    parseFloat(headerParts[3]) * BOHR_TO_ANGSTROM,
  ];

  const dims: [number, number, number] = [0, 0, 0];
  const axesAngstrom: [
    [number, number, number],
    [number, number, number],
    [number, number, number],
  ] = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];

  for (let i = 0; i < 3; i++) {
    const p = lines[3 + i].trim().split(/\s+/);
    const n = Math.abs(parseInt(p[0], 10));
    dims[i] = n;
    const rawN = parseInt(p[0], 10);
    // Gaussian convention: negative axis count already means Angstrom, positive means Bohr
    const scale = rawN < 0 ? 1.0 : BOHR_TO_ANGSTROM;
    axesAngstrom[i] = [
      parseFloat(p[1]) * scale,
      parseFloat(p[2]) * scale,
      parseFloat(p[3]) * scale,
    ];
  }

  const atoms: GaussianCubeData["atoms"] = [];
  for (let i = 0; i < nAtoms; i++) {
    const line = lines[6 + i]?.trim();
    if (!line) continue;
    const p = line.split(/\s+/);
    atoms.push({
      z: parseInt(p[0], 10),
      charge: parseFloat(p[1]),
      posAngstrom: [
        parseFloat(p[2]) * BOHR_TO_ANGSTROM,
        parseFloat(p[3]) * BOHR_TO_ANGSTROM,
        parseFloat(p[4]) * BOHR_TO_ANGSTROM,
      ],
    });
  }

  let dataStartLine = 6 + nAtoms;
  if (hasMoHeader && dataStartLine < lines.length) {
    // Check if next line holds integer MO metadata (e.g. `1  142`)
    const toks = lines[dataStartLine].trim().split(/\s+/);
    if (toks.length >= 2 && toks.every((t) => /^-?\d+$/.test(t))) {
      dataStartLine += 1;
    }
  }

  const total = dims[0] * dims[1] * dims[2];
  const values = new Float32Array(total);
  let k = 0;
  let minVal = Infinity;
  let maxVal = -Infinity;

  for (let li = dataStartLine; li < lines.length && k < total; li++) {
    const trimmed = lines[li].trim();
    if (!trimmed) continue;
    const toks = trimmed.split(/\s+/);
    for (let t = 0; t < toks.length && k < total; t++) {
      const v = parseFloat(toks[t]);
      if (Number.isFinite(v)) {
        values[k++] = v;
        if (v < minVal) minVal = v;
        if (v > maxVal) maxVal = v;
      }
    }
  }
  if (k < total) {
    throw new Error(`.cub 格点数据不完整: 预期 ${total}，实读 ${k}`);
  }

  return {
    comment1,
    comment2,
    dims,
    originAngstrom,
    axesAngstrom,
    atoms,
    values,
    minVal,
    maxVal,
  };
}

/** Sample scalar value at continuous world coordinates (Angstrom) via trilinear interpolation. */
export function sampleCubeTrilinear(cube: GaussianCubeData, x: number, y: number, z: number): number {
  const [nx, ny, nz] = cube.dims;
  const o = cube.originAngstrom;
  const [a0, a1, a2] = cube.axesAngstrom;

  // Invert 3x3 column basis [a0 | a1 | a2]
  const dx = x - o[0];
  const dy = y - o[1];
  const dz = z - o[2];

  const c00 = a1[1] * a2[2] - a1[2] * a2[1];
  const c01 = a1[2] * a2[0] - a1[0] * a2[2];
  const c02 = a1[0] * a2[1] - a1[1] * a2[0];
  const det = a0[0] * c00 + a0[1] * c01 + a0[2] * c02;
  if (Math.abs(det) < 1e-18) return 0;

  let fi = (dx * c00 + dy * c01 + dz * c02) / det;
  let fj =
    (dx * (a2[1] * a0[2] - a2[2] * a0[1]) +
      dy * (a2[2] * a0[0] - a2[0] * a0[2]) +
      dz * (a2[0] * a0[1] - a2[1] * a0[0])) /
    det;
  let fk =
    (dx * (a0[1] * a1[2] - a0[2] * a1[1]) +
      dy * (a0[2] * a1[0] - a0[0] * a1[2]) +
      dz * (a0[0] * a1[1] - a0[1] * a1[0])) /
    det;

  fi = Math.max(0, Math.min(nx - 1.0001, fi));
  fj = Math.max(0, Math.min(ny - 1.0001, fj));
  fk = Math.max(0, Math.min(nz - 1.0001, fk));

  const i0 = Math.floor(fi);
  const j0 = Math.floor(fj);
  const k0 = Math.floor(fk);
  const i1 = Math.min(nx - 1, i0 + 1);
  const j1 = Math.min(ny - 1, j0 + 1);
  const k1 = Math.min(nz - 1, k0 + 1);
  const tx = fi - i0;
  const ty = fj - j0;
  const tz = fk - k0;

  const idx = (i: number, j: number, k: number) => (i * ny + j) * nz + k;
  const v000 = cube.values[idx(i0, j0, k0)];
  const v001 = cube.values[idx(i0, j0, k1)];
  const v010 = cube.values[idx(i0, j1, k0)];
  const v011 = cube.values[idx(i0, j1, k1)];
  const v100 = cube.values[idx(i1, j0, k0)];
  const v101 = cube.values[idx(i1, j0, k1)];
  const v110 = cube.values[idx(i1, j1, k0)];
  const v111 = cube.values[idx(i1, j1, k1)];

  const c00v = v000 * (1 - tz) + v001 * tz;
  const c01v = v010 * (1 - tz) + v011 * tz;
  const c10v = v100 * (1 - tz) + v101 * tz;
  const c11v = v110 * (1 - tz) + v111 * tz;
  const c0v = c00v * (1 - ty) + c01v * ty;
  const c1v = c10v * (1 - ty) + c11v * ty;
  return c0v * (1 - tx) + c1v * tx;
}

/** Map scalar value against locked absolute [minVal, maxVal] range using VMD BWR / RWB / Viridis LUTs. */
export function mapScalarToColor(
  val: number,
  minVal: number,
  maxVal: number,
  palette: SurfaceColormap
): [number, number, number] {
  const span = maxVal - minVal;
  const t = span > 1e-12 ? Math.max(0, Math.min(1, (val - minVal) / span)) : 0.5;

  if (palette === "BWR") {
    // Verified VMD BWR convention: (0.1,0.1,1.0) Blue -> (1,1,1) Pure White -> (1.0,0.1,0.1) Red
    if (t <= 0.5) {
      const s = t * 2.0;
      return [0.1 + 0.9 * s, 0.1 + 0.9 * s, 1.0];
    }
    const s = (t - 0.5) * 2.0;
    return [1.0, 1.0 - 0.9 * s, 1.0 - 0.9 * s];
  }
  if (palette === "RWB") {
    if (t <= 0.5) {
      const s = t * 2.0;
      return [1.0, 0.1 + 0.9 * s, 0.1 + 0.9 * s];
    }
    const s = (t - 0.5) * 2.0;
    return [1.0 - 0.9 * s, 1.0 - 0.9 * s, 1.0];
  }
  // Viridis 5-stop piecewise linear approximation
  const stops: Array<[number, number, number]> = [
    [0.267, 0.005, 0.329],
    [0.23, 0.322, 0.545],
    [0.129, 0.569, 0.549],
    [0.369, 0.788, 0.384],
    [0.993, 0.906, 0.144],
  ];
  const x = t * 4;
  const i = Math.min(3, Math.floor(x));
  const f = x - i;
  return [
    stops[i][0] + (stops[i + 1][0] - stops[i][0]) * f,
    stops[i][1] + (stops[i + 1][1] - stops[i][1]) * f,
    stops[i][2] + (stops[i + 1][2] - stops[i][2]) * f,
  ];
}

// 6 tetrahedra decomposing the unit cube [0..7]
const TETRAHEDRA: ReadonlyArray<readonly [number, number, number, number]> = [
  [0, 5, 1, 6],
  [0, 1, 2, 6],
  [0, 2, 3, 6],
  [0, 3, 7, 6],
  [0, 7, 4, 6],
  [0, 4, 5, 6],
];

const CUBE_OFFSETS: ReadonlyArray<readonly [number, number, number]> = [
  [0, 0, 0], // 0
  [1, 0, 0], // 1
  [1, 1, 0], // 2
  [0, 1, 0], // 3
  [0, 0, 1], // 4
  [1, 0, 1], // 5
  [1, 1, 1], // 6
  [0, 1, 1], // 7
];

function extractMarchingTetrahedra(
  cube: GaussianCubeData,
  isovalue: number,
  opacity: number,
  colorFn: (pos: [number, number, number], val: number) => [number, number, number],
  name: string
): SurfaceMeshData {
  const [nx, ny, nz] = cube.dims;
  const totalPts = nx * ny * nz;
  // Adaptive stride prevents GPU buffer blowup on huge >1.5M grids while keeping full detail below
  const stride = totalPts > 1_500_000 ? 2 : 1;

  const o = cube.originAngstrom;
  const [a0, a1, a2] = cube.axesAngstrom;
  const vals = cube.values;
  const idx = (i: number, j: number, k: number) => (i * ny + j) * nz + k;

  const gridPos = (i: number, j: number, k: number): [number, number, number] => [
    o[0] + i * a0[0] + j * a1[0] + k * a2[0],
    o[1] + i * a0[1] + j * a1[1] + k * a2[1],
    o[2] + i * a0[2] + j * a1[2] + k * a2[2],
  ];

  // Central-difference gradient in index space mapped via basis norm
  const gradAt = (i: number, j: number, k: number): [number, number, number] => {
    const im = Math.max(0, i - 1);
    const ip = Math.min(nx - 1, i + 1);
    const jm = Math.max(0, j - 1);
    const jp = Math.min(ny - 1, j + 1);
    const km = Math.max(0, k - 1);
    const kp = Math.min(nz - 1, k + 1);
    const gx = -(vals[idx(ip, j, k)] - vals[idx(im, j, k)]);
    const gy = -(vals[idx(i, jp, k)] - vals[idx(i, jm, k)]);
    const gz = -(vals[idx(i, j, kp)] - vals[idx(i, j, km)]);
    const l = Math.hypot(gx, gy, gz);
    return l > 1e-12 ? [gx / l, gy / l, gz / l] : [0, 0, 1];
  };

  const outVerts: number[] = [];
  const outWorld: number[] = [];

  const cornerP: Array<[number, number, number]> = new Array(8);
  const cornerN: Array<[number, number, number]> = new Array(8);
  const cornerV = new Float64Array(8);

  const pushInterp = (a: number, b: number) => {
    const va = cornerV[a];
    const vb = cornerV[b];
    const denom = vb - va;
    const t = Math.abs(denom) > 1e-12 ? (isovalue - va) / denom : 0.5;
    const tt = Math.max(0, Math.min(1, t));
    const px = cornerP[a][0] + (cornerP[b][0] - cornerP[a][0]) * tt;
    const py = cornerP[a][1] + (cornerP[b][1] - cornerP[a][1]) * tt;
    const pz = cornerP[a][2] + (cornerP[b][2] - cornerP[a][2]) * tt;
    const nxv = cornerN[a][0] + (cornerN[b][0] - cornerN[a][0]) * tt;
    const nyv = cornerN[a][1] + (cornerN[b][1] - cornerN[a][1]) * tt;
    const nzv = cornerN[a][2] + (cornerN[b][2] - cornerN[a][2]) * tt;
    const nl = Math.hypot(nxv, nyv, nzv) || 1;
    const pos: [number, number, number] = [px, py, pz];
    const [r, g, bCol] = colorFn(pos, isovalue);
    outVerts.push(px, py, pz, nxv / nl, nyv / nl, nzv / nl, r, g, bCol, opacity);
    outWorld.push(px, py, pz);
  };

  const pushTri = (
    e0a: number,
    e0b: number,
    e1a: number,
    e1b: number,
    e2a: number,
    e2b: number
  ) => {
    pushInterp(e0a, e0b);
    pushInterp(e1a, e1b);
    pushInterp(e2a, e2b);
  };

  for (let i = 0; i + stride < nx; i += stride) {
    for (let j = 0; j + stride < ny; j += stride) {
      for (let k = 0; k + stride < nz; k += stride) {
        let below = 0;
        let above = 0;
        for (let c = 0; c < 8; c++) {
          const [oi, oj, ok] = CUBE_OFFSETS[c];
          const ii = i + oi * stride;
          const jj = j + oj * stride;
          const kk = k + ok * stride;
          const v = vals[idx(ii, jj, kk)];
          cornerV[c] = v;
          if (v < isovalue) below++;
          else above++;
        }
        if (below === 0 || above === 0) continue;

        for (let c = 0; c < 8; c++) {
          const [oi, oj, ok] = CUBE_OFFSETS[c];
          const ii = i + oi * stride;
          const jj = j + oj * stride;
          const kk = k + ok * stride;
          cornerP[c] = gridPos(ii, jj, kk);
          cornerN[c] = gradAt(ii, jj, kk);
        }

        for (const tet of TETRAHEDRA) {
          const ins: number[] = [];
          const outs: number[] = [];
          for (let ti = 0; ti < 4; ti++) {
            const c = tet[ti];
            if (cornerV[c] >= isovalue) ins.push(c);
            else outs.push(c);
          }
          if (ins.length === 0 || outs.length === 0) continue;
          if (ins.length === 1) {
            const a = ins[0];
            pushTri(a, outs[0], a, outs[1], a, outs[2]);
          } else if (ins.length === 3) {
            const a = outs[0];
            pushTri(a, ins[0], a, ins[1], a, ins[2]);
          } else if (ins.length === 2) {
            const [a, b] = ins;
            const [c, d] = outs;
            pushTri(a, c, a, d, b, c);
            pushTri(b, c, a, d, b, d);
          }
        }
      }
    }
  }

  return {
    name,
    vertices: new Float32Array(outVerts),
    vertexCount: Math.floor(outVerts.length / 10),
    worldPoints: new Float32Array(outWorld),
  };
}

/** Extract +/- orbital lobes (`+` green `#22c55e`, `-` blue `#3b82f6`). */
export function buildOrbitalSurfaceMeshes(
  moCube: GaussianCubeData,
  isovalue = 0.03,
  opacity = 0.78
): SurfaceMeshData[] {
  const iso = Math.max(1e-5, Math.abs(isovalue));
  const posMesh = extractMarchingTetrahedra(
    moCube,
    iso,
    opacity,
    () => [0.133, 0.773, 0.369],
    "MO (+)"
  );
  const negMesh = extractMarchingTetrahedra(
    moCube,
    -iso,
    opacity,
    () => [0.231, 0.51, 0.965],
    "MO (-)"
  );
  return [posMesh, negMesh].filter((m) => m.vertexCount > 0);
}

/** Extract density isosurface colored by absolute ESP scalar field (`minAu..maxAu`). */
export function buildEspSurfaceMesh(
  densityCube: GaussianCubeData,
  espCube: GaussianCubeData,
  isoDensity = 0.001,
  minAu = -0.042,
  maxAu = 0.028,
  palette: SurfaceColormap = "BWR",
  opacity = 0.72
): SurfaceMeshData {
  return extractMarchingTetrahedra(
    densityCube,
    Math.max(1e-6, isoDensity),
    opacity,
    (pos) => {
      const espVal = sampleCubeTrilinear(espCube, pos[0], pos[1], pos[2]);
      return mapScalarToColor(espVal, minAu, maxAu, palette);
    },
    "ESP Surface"
  );
}
