export type Vec3 = [number, number, number];
export type Mat3 = [Vec3, Vec3, Vec3];

export type ScientificCameraPreset =
  | "vertical_front"
  | "horizontal_front"
  | "side_edge"
  | "paper_oblique";

function dot3(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross3(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function norm3(v: Vec3): Vec3 {
  const l = Math.hypot(v[0], v[1], v[2]);
  return l > 1e-12 ? [v[0] / l, v[1] / l, v[2] / l] : [0, 0, 1];
}

function mulMat3(a: Mat3, b: Mat3): Mat3 {
  const out: Mat3 = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      out[r][c] = a[r][0] * b[0][c] + a[r][1] * b[1][c] + a[r][2] * b[2][c];
    }
  }
  return out;
}

function rotX(deg: number): Mat3 {
  const t = (deg * Math.PI) / 180;
  const c = Math.cos(t);
  const s = Math.sin(t);
  return [
    [1, 0, 0],
    [0, c, -s],
    [0, s, c],
  ];
}

function rotZ(deg: number): Mat3 {
  const t = (deg * Math.PI) / 180;
  const c = Math.cos(t);
  const s = Math.sin(t);
  return [
    [c, -s, 0],
    [s, c, 0],
    [0, 0, 1],
  ];
}

/** Pure-TS heavy-atom PCA canonical frame fallback: long -> +Y, mid -> -X, normal -> +Z (SO(3)). */
export function computeHeavyAtomCanonicalR(
  coords: Float32Array,
  numAtoms: number,
  atomicNumbers?: Uint8Array
): Mat3 {
  const indices: number[] = [];
  for (let i = 0; i < numAtoms; i++) {
    if (!atomicNumbers || atomicNumbers[i] > 1) indices.push(i);
  }
  if (indices.length < 3) {
    indices.length = 0;
    for (let i = 0; i < numAtoms; i++) indices.push(i);
  }
  if (indices.length < 2) {
    return [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ];
  }

  let mx = 0,
    my = 0,
    mz = 0;
  for (const i of indices) {
    mx += coords[i * 3];
    my += coords[i * 3 + 1];
    mz += coords[i * 3 + 2];
  }
  const invN = 1 / indices.length;
  mx *= invN;
  my *= invN;
  mz *= invN;

  const a = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];
  for (const i of indices) {
    const dx = coords[i * 3] - mx;
    const dy = coords[i * 3 + 1] - my;
    const dz = coords[i * 3 + 2] - mz;
    const d = [dx, dy, dz];
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) {
        a[r][c] += d[r] * d[c];
      }
    }
  }

  const v = [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ];
  for (let sweep = 0; sweep < 36; sweep++) {
    let p = 0,
      q = 1,
      maxOff = Math.abs(a[0][1]);
    for (const [ii, jj] of [
      [0, 2],
      [1, 2],
    ] as const) {
      if (Math.abs(a[ii][jj]) > maxOff) {
        maxOff = Math.abs(a[ii][jj]);
        p = ii;
        q = jj;
      }
    }
    if (maxOff < 1e-11) break;
    const tau = (a[q][q] - a[p][p]) / (2 * a[p][q]);
    const t =
      tau >= 0
        ? 1 / (tau + Math.sqrt(1 + tau * tau))
        : -1 / (-tau + Math.sqrt(1 + tau * tau));
    const c = 1 / Math.sqrt(1 + t * t);
    const s = t * c;
    const app = a[p][p];
    const aqq = a[q][q];
    const apq = a[p][q];
    a[p][p] = app - t * apq;
    a[q][q] = aqq + t * apq;
    a[p][q] = 0;
    a[q][p] = 0;
    const r = 3 - p - q;
    const arp = a[r][p];
    const arq = a[r][q];
    a[r][p] = c * arp - s * arq;
    a[p][r] = a[r][p];
    a[r][q] = s * arp + c * arq;
    a[q][r] = a[r][q];
    for (let row = 0; row < 3; row++) {
      const vp = v[row][p];
      const vq = v[row][q];
      v[row][p] = c * vp - s * vq;
      v[row][q] = s * vp + c * vq;
    }
  }

  const evals = [a[0][0], a[1][1], a[2][2]];
  const order = [0, 1, 2].sort((i, j) => evals[j] - evals[i]);
  const eLong = norm3([v[0][order[0]], v[1][order[0]], v[2][order[0]]]);
  const eMid = norm3([v[0][order[1]], v[1][order[1]], v[2][order[1]]]);
  let eShort = norm3([v[0][order[2]], v[1][order[2]], v[2][order[2]]]);
  if (dot3(cross3(eLong, eMid), eShort) < 0) {
    eShort = [-eShort[0], -eShort[1], -eShort[2]];
  }
  return [
    [-eMid[0], -eMid[1], -eMid[2]],
    eLong,
    eShort,
  ];
}

export class OrbitCamera {
  target: Vec3 = [0, 0, 0];
  distance = 16;
  yaw = 0.55;
  pitch = 0.35;
  fovRad = (38 * Math.PI) / 180;
  // 三向与科研标准视图使用严格正交投影（无透视缩短，键长可直接目视比较）
  orthographic = false;
  private customBasis: { right: Vec3; up: Vec3; forward: Vec3 } | null = null;

  fit(center: Vec3, boundingRadius: number) {
    this.customBasis = null;
    this.target = [...center];
    const r = Math.max(2.0, boundingRadius);
    this.distance = (r / Math.sin(this.fovRad * 0.5)) * 1.08;
    this.yaw = 0.55;
    this.pitch = 0.35;
    this.orthographic = false;
  }

  setFrontView() {
    this.customBasis = null;
    this.yaw = 0;
    this.pitch = 0;
    this.orthographic = true;
  }

  setTopView() {
    this.customBasis = null;
    this.yaw = 0;
    this.pitch = Math.PI / 2 - 0.0001;
    this.orthographic = true;
  }

  setSideView() {
    this.customBasis = null;
    this.yaw = Math.PI * 0.5;
    this.pitch = 0;
    this.orthographic = true;
  }

  /**
   * Apply Core-First deterministic frame + one of the 4 standard research camera presets
   * and automatically compute orthographic framing so the molecule fills `fillRatio` (85%-90%).
   */
  applyScientificPreset(
    preset: ScientificCameraPreset,
    coords: Float32Array,
    numAtoms: number,
    canvasWidth: number,
    canvasHeight: number,
    canonicalR?: Mat3,
    atomicNumbers?: Uint8Array,
    extraWorldPoints?: Float32Array,
    fillRatio = 0.88
  ) {
    const rCan = canonicalR ?? computeHeavyAtomCanonicalR(coords, numAtoms, atomicNumbers);
    const xC = rCan[0];
    const yC = rCan[1];
    const zC = rCan[2];

    let right: Vec3;
    let up: Vec3;
    let forward: Vec3;

    if (preset === "vertical_front") {
      right = xC;
      up = yC;
      forward = [-zC[0], -zC[1], -zC[2]];
    } else if (preset === "horizontal_front") {
      right = yC;
      up = [-xC[0], -xC[1], -xC[2]];
      forward = [-zC[0], -zC[1], -zC[2]];
    } else if (preset === "side_edge") {
      right = yC;
      up = zC;
      forward = [-xC[0], -xC[1], -xC[2]];
    } else {
      // paper_oblique: rot_x(-35°) @ rot_z(-78°) on canonical Core-First frame
      const l = mulMat3(rotX(-35.0), rotZ(-(90.0 - 12.0)));
      const camMat = mulMat3(l, rCan);
      right = norm3(camMat[0]);
      up = norm3(camMat[1]);
      const negF = norm3(camMat[2]);
      forward = [-negF[0], -negF[1], -negF[2]];
    }

    this.customBasis = { right, up, forward };
    this.orthographic = true;

    const negForward: Vec3 = [-forward[0], -forward[1], -forward[2]];
    let minU = Infinity,
      maxU = -Infinity,
      minV = Infinity,
      maxV = -Infinity,
      minW = Infinity,
      maxW = -Infinity;

    const scan = (pts: Float32Array, count: number, stride = 3) => {
      for (let i = 0; i < count; i++) {
        const x = pts[i * stride];
        const y = pts[i * stride + 1];
        const z = pts[i * stride + 2];
        const u = x * right[0] + y * right[1] + z * right[2];
        const v = x * up[0] + y * up[1] + z * up[2];
        const w = x * negForward[0] + y * negForward[1] + z * negForward[2];
        if (u < minU) minU = u;
        if (u > maxU) maxU = u;
        if (v < minV) minV = v;
        if (v > maxV) maxV = v;
        if (w < minW) minW = w;
        if (w > maxW) maxW = w;
      }
    };

    if (numAtoms > 0) {
      scan(coords, numAtoms, 3);
    }
    if (extraWorldPoints && extraWorldPoints.length >= 3) {
      scan(extraWorldPoints, Math.floor(extraWorldPoints.length / 3), 3);
    }

    if (!Number.isFinite(minU)) {
      this.target = [0, 0, 0];
      this.distance = 16;
      return;
    }

    const uc = 0.5 * (minU + maxU);
    const vc = 0.5 * (minV + maxV);
    const wc = 0.5 * (minW + maxW);
    this.target = [
      uc * right[0] + vc * up[0] + wc * negForward[0],
      uc * right[1] + vc * up[1] + wc * negForward[1],
      uc * right[2] + vc * up[2] + wc * negForward[2],
    ];

    const spanU = Math.max(2.0, maxU - minU + 1.8);
    const spanV = Math.max(2.0, maxV - minV + 1.8);
    const aspect = Math.max(0.1, canvasWidth / Math.max(1, canvasHeight));
    const fill = Math.max(0.5, Math.min(0.95, fillRatio));
    const reqHalfH = Math.max(spanV / (2 * fill), spanU / (2 * fill * aspect));
    this.distance = Math.max(3.0, reqHalfH / Math.tan(this.fovRad * 0.5));
  }

  orbit(dx: number, dy: number) {
    if (this.customBasis) {
      // Initialize yaw/pitch smoothly from current forward vector before switching back to spherical orbit
      const f = this.customBasis.forward;
      this.pitch = Math.asin(Math.max(-0.99, Math.min(0.99, -f[1])));
      this.yaw = Math.atan2(-f[0], -f[2]);
      this.customBasis = null;
    }
    this.yaw -= dx * 0.0065;
    this.pitch = Math.max(-1.52, Math.min(1.52, this.pitch + dy * 0.0065));
    this.orthographic = false;
  }

  pan(dx: number, dy: number, viewportHeight: number) {
    const scale = (2 * this.distance * Math.tan(this.fovRad * 0.5)) / Math.max(1, viewportHeight);
    const { right, up } = this.basis();
    this.target[0] -= right[0] * dx * scale - up[0] * dy * scale;
    this.target[1] -= right[1] * dx * scale - up[1] * dy * scale;
    this.target[2] -= right[2] * dx * scale - up[2] * dy * scale;
  }

  zoom(deltaY: number) {
    const factor = Math.exp(deltaY * 0.0012);
    this.distance = Math.max(1.5, Math.min(5000, this.distance * factor));
  }

  basis() {
    if (this.customBasis) {
      const { right, up, forward } = this.customBasis;
      const eye: Vec3 = [
        this.target[0] - forward[0] * this.distance,
        this.target[1] - forward[1] * this.distance,
        this.target[2] - forward[2] * this.distance,
      ];
      return {
        eye,
        forward: [...forward] as Vec3,
        right: [...right] as Vec3,
        up: [...up] as Vec3,
      };
    }

    const cp = Math.cos(this.pitch);
    const sp = Math.sin(this.pitch);
    const cy = Math.cos(this.yaw);
    const sy = Math.sin(this.yaw);
    const forward: Vec3 = [-cp * sy, -sp, -cp * cy];
    const eye: Vec3 = [
      this.target[0] - forward[0] * this.distance,
      this.target[1] - forward[1] * this.distance,
      this.target[2] - forward[2] * this.distance,
    ];
    const rx = -forward[2];
    const rz = forward[0];
    const rl = Math.hypot(rx, rz) || 1;
    const right: Vec3 = [rx / rl, 0, rz / rl];
    const up: Vec3 = [
      right[1] * forward[2] - right[2] * forward[1],
      right[2] * forward[0] - right[0] * forward[2],
      right[0] * forward[1] - right[1] * forward[0],
    ];
    return { eye, forward, right, up };
  }

  viewMatrix(): Float32Array {
    const { eye, forward, right, up } = this.basis();
    const zx = -forward[0],
      zy = -forward[1],
      zz = -forward[2];
    return new Float32Array([
      right[0],
      up[0],
      zx,
      0,
      right[1],
      up[1],
      zy,
      0,
      right[2],
      up[2],
      zz,
      0,
      -(right[0] * eye[0] + right[1] * eye[1] + right[2] * eye[2]),
      -(up[0] * eye[0] + up[1] * eye[1] + up[2] * eye[2]),
      -(zx * eye[0] + zy * eye[1] + zz * eye[2]),
      1,
    ]);
  }

  projMatrix(aspect: number): Float32Array {
    const near = Math.max(0.1, this.distance * 0.02);
    const far = Math.max(200, this.distance * 10);
    if (this.orthographic) {
      const halfH = this.distance * Math.tan(this.fovRad * 0.5);
      const halfW = halfH * Math.max(0.1, aspect);
      const nf = 1 / (near - far);
      return new Float32Array([
        1 / halfW, 0, 0, 0,
        0, 1 / halfH, 0, 0,
        0, 0, nf, 0,
        0, 0, near * nf, 1,
      ]);
    }
    const f = 1.0 / Math.tan(this.fovRad * 0.5);
    const nf = 1 / (near - far);
    return new Float32Array([
      f / Math.max(0.1, aspect),
      0,
      0,
      0,
      0,
      f,
      0,
      0,
      0,
      0,
      far * nf,
      -1,
      0,
      0,
      far * near * nf,
      0,
    ]);
  }

  projectWorldToScreen(
    pos: Vec3,
    width: number,
    height: number
  ): { x: number; y: number; ndcZ: number; visible: boolean } {
    const view = this.viewMatrix();
    const proj = this.projMatrix(width / Math.max(1, height));
    const vx = view[0] * pos[0] + view[4] * pos[1] + view[8] * pos[2] + view[12];
    const vy = view[1] * pos[0] + view[5] * pos[1] + view[9] * pos[2] + view[13];
    const vz = view[2] * pos[0] + view[6] * pos[1] + view[10] * pos[2] + view[14];

    const cx = proj[0] * vx + proj[4] * vy + proj[8] * vz + proj[12];
    const cy = proj[1] * vx + proj[5] * vy + proj[9] * vz + proj[13];
    const cz = proj[2] * vx + proj[6] * vy + proj[10] * vz + proj[14];
    const cw = proj[3] * vx + proj[7] * vy + proj[11] * vz + proj[15];

    if (cw <= 1e-6) {
      return { x: 0, y: 0, ndcZ: 2, visible: false };
    }
    const nx = cx / cw;
    const ny = cy / cw;
    const nz = cz / cw;
    return {
      x: (nx + 1) * 0.5 * width,
      y: (1 - ny) * 0.5 * height,
      ndcZ: nz,
      visible: nz >= 0 && nz <= 1,
    };
  }

  pickRay(
    ndcX: number,
    ndcY: number,
    aspect: number
  ): { origin: Vec3; dir: Vec3 } {
    const { eye, forward, right, up } = this.basis();
    if (this.orthographic) {
      const halfH = this.distance * Math.tan(this.fovRad * 0.5);
      const halfW = halfH * Math.max(0.1, aspect);
      const ox = eye[0] + right[0] * ndcX * halfW + up[0] * ndcY * halfH;
      const oy = eye[1] + right[1] * ndcX * halfW + up[1] * ndcY * halfH;
      const oz = eye[2] + right[2] * ndcX * halfW + up[2] * ndcY * halfH;
      return { origin: [ox, oy, oz], dir: [...forward] };
    }
    const tanHalf = Math.tan(this.fovRad * 0.5);
    const dx = forward[0] + right[0] * (ndcX * aspect * tanHalf) + up[0] * (ndcY * tanHalf);
    const dy = forward[1] + right[1] * (ndcX * aspect * tanHalf) + up[1] * (ndcY * tanHalf);
    const dz = forward[2] + right[2] * (ndcX * aspect * tanHalf) + up[2] * (ndcY * tanHalf);
    const len = Math.hypot(dx, dy, dz) || 1;
    return { origin: eye, dir: [dx / len, dy / len, dz / len] };
  }
}

export function rayPickAtom(
  origin: Vec3,
  dir: Vec3,
  coords: Float32Array,
  radii: Float32Array,
  numAtoms: number
): number {
  let bestIdx = -1;
  let bestT = Infinity;
  const [ox, oy, oz] = origin;
  const [dx, dy, dz] = dir;
  for (let i = 0; i < numAtoms; i++) {
    const r = radii[i];
    if (r <= 0.001) continue;
    const hitR = Math.max(r * 1.25, 0.35);
    const ocx = coords[i * 3] - ox;
    const ocy = coords[i * 3 + 1] - oy;
    const ocz = coords[i * 3 + 2] - oz;
    const tca = ocx * dx + ocy * dy + ocz * dz;
    if (tca <= 0) continue;
    const oc2 = ocx * ocx + ocy * ocy + ocz * ocz;
    const d2 = oc2 - tca * tca;
    const r2 = hitR * hitR;
    if (d2 <= r2) {
      const thc = Math.sqrt(Math.max(0, r2 - d2));
      const t = tca - thc;
      if (t > 0 && t < bestT) {
        bestT = t;
        bestIdx = i;
      }
    }
  }
  return bestIdx;
}
