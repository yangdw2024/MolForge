export class OrbitCamera {
  target: [number, number, number] = [0, 0, 0];
  distance = 16;
  yaw = 0.55;
  pitch = 0.35;
  fovRad = (38 * Math.PI) / 180;
  // 三向标准视图使用严格正交投影（无透视缩短，键长可直接目视比较）
  orthographic = false;

  fit(center: [number, number, number], boundingRadius: number) {
    this.target = [...center];
    const r = Math.max(2.0, boundingRadius);
    this.distance = (r / Math.sin(this.fovRad * 0.5)) * 1.08;
    this.yaw = 0.55;
    this.pitch = 0.35;
    this.orthographic = false;
  }

  setFrontView() {
    this.yaw = 0;
    this.pitch = 0;
    this.orthographic = true;
  }

  setTopView() {
    this.yaw = 0;
    this.pitch = Math.PI / 2 - 0.0001;
    this.orthographic = true;
  }

  setSideView() {
    this.yaw = Math.PI * 0.5;
    this.pitch = 0;
    this.orthographic = true;
  }

  orbit(dx: number, dy: number) {
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
    const cp = Math.cos(this.pitch);
    const sp = Math.sin(this.pitch);
    const cy = Math.cos(this.yaw);
    const sy = Math.sin(this.yaw);
    const forward: [number, number, number] = [-cp * sy, -sp, -cp * cy];
    const eye: [number, number, number] = [
      this.target[0] - forward[0] * this.distance,
      this.target[1] - forward[1] * this.distance,
      this.target[2] - forward[2] * this.distance,
    ];
    // right = normalize(forward x worldUp)
    const rx = -forward[2];
    const rz = forward[0];
    const rl = Math.hypot(rx, rz) || 1;
    const right: [number, number, number] = [rx / rl, 0, rz / rl];
    // up = cross(right, forward)
    const up: [number, number, number] = [
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
    // Column-major 4x4 for WGSL
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
      // 严格正交：半高由当前 distance+fov 决定，保证切换视图时分子大小连续
      const halfH = this.distance * Math.tan(this.fovRad * 0.5);
      const halfW = halfH * Math.max(0.1, aspect);
      const nf = 1 / (near - far);
      // WebGPU NDC Z in [0, 1]
      return new Float32Array([
        1 / halfW, 0, 0, 0,
        0, 1 / halfH, 0, 0,
        0, 0, nf, 0,
        0, 0, near * nf, 1,
      ]);
    }
    const f = 1.0 / Math.tan(this.fovRad * 0.5);
    // WebGPU NDC Z in [0, 1]
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

  pickRay(
    ndcX: number,
    ndcY: number,
    aspect: number
  ): { origin: [number, number, number]; dir: [number, number, number] } {
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
  origin: [number, number, number],
  dir: [number, number, number],
  coords: Float32Array,
  radii: Float32Array,
  numAtoms: number
): number {
  let bestIdx = -1;
  let bestT = Infinity;
  const ox = origin[0],
    oy = origin[1],
    oz = origin[2];
  const dx = dir[0],
    dy = dir[1],
    dz = dir[2];
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
