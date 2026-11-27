import { OrbitCamera, rayPickAtom } from "./camera";
import { CELL_LINE_WGSL, CYLINDER_WGSL, SPHERE_WGSL } from "./shaders";
import type { BinaryMoleculeData, RepresentationMode } from "../types/molforge";

export interface EngineTelemetry {
  backend: "WebGPU" | "Canvas2D Fallback";
  gpuName: string;
  fps: number;
  uploadMs: number;
  drawMs: number;
}

export class WebGPUMolEngine {
  private canvas: HTMLCanvasElement;
  private ctx2d: CanvasRenderingContext2D | null = null;
  private gpuCtx: GPUCanvasContext | null = null;
  private device: GPUDevice | null = null;
  private format: GPUTextureFormat = "bgra8unorm";
  private depthTexture: GPUTexture | null = null;

  private spherePipeline: GPURenderPipeline | null = null;
  private cylinderPipeline: GPURenderPipeline | null = null;
  private cellPipeline: GPURenderPipeline | null = null;

  private uniformBuffer: GPUBuffer | null = null;
  private sphereBindGroup: GPUBindGroup | null = null;
  private cylinderBindGroup: GPUBindGroup | null = null;
  private cellBindGroup: GPUBindGroup | null = null;

  private atomBuffer: GPUBuffer | null = null;
  private bondBuffer: GPUBuffer | null = null;
  private cellBuffer: GPUBuffer | null = null;

  private atomCount = 0;
  private bondCount = 0;
  private cellVertCount = 0;

  private data: BinaryMoleculeData | null = null;
  private effectiveRadii = new Float32Array(0);
  private mode: RepresentationMode = "ball_stick";
  private atomScale = 1.0;
  private bondScale = 1.0;
  private showHydrogens = true;
  private showCell = true;
  private selectedIndices = new Set<number>();
  private darkBg = true;

  public camera = new OrbitCamera();
  private rafId = 0;
  private dirty = true;
  private destroyed = false;
  private lastFpsStamp = performance.now();
  private frameCounter = 0;
  private telemetry: EngineTelemetry = {
    backend: "Canvas2D Fallback",
    gpuName: "Initializing...",
    fps: 60,
    uploadMs: 0,
    drawMs: 0,
  };
  private onTelemetry?: (t: EngineTelemetry) => void;

  constructor(canvas: HTMLCanvasElement, onTelemetry?: (t: EngineTelemetry) => void) {
    this.canvas = canvas;
    this.onTelemetry = onTelemetry;
  }

  async init(): Promise<void> {
    if (typeof navigator !== "undefined" && "gpu" in navigator && navigator.gpu) {
      try {
        const adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" });
        if (adapter) {
          const device = await adapter.requestDevice();
          const ctx = this.canvas.getContext("webgpu");
          if (ctx) {
            this.device = device;
            this.gpuCtx = ctx;
            this.format = navigator.gpu.getPreferredCanvasFormat();
            ctx.configure({ device, format: this.format, alphaMode: "premultiplied" });
            const info = (adapter as unknown as { info?: { device?: string; vendor?: string; description?: string } }).info;
            const gpuName =
              info?.description || info?.device || (info?.vendor ? `${info.vendor} WebGPU` : "WebGPU Hardware Adapter");
            this.telemetry.backend = "WebGPU";
            this.telemetry.gpuName = gpuName;
            this.createPipelines(device);
            this.onTelemetry?.({ ...this.telemetry });
            this.rebuildBuffers();
            this.startLoop();
            return;
          }
        }
      } catch {
        // Fallback smoothly below
      }
    }
    this.ctx2d = this.canvas.getContext("2d");
    this.telemetry.backend = "Canvas2D Fallback";
    this.telemetry.gpuName = "Software 2D Stage (No WebGPU)";
    this.onTelemetry?.({ ...this.telemetry });
    this.startLoop();
  }

  private createPipelines(device: GPUDevice) {
    const uniformLayout = device.createBindGroupLayout({
      entries: [{ binding: 0, visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT, buffer: { type: "uniform" } }],
    });
    const pipelineLayout = device.createPipelineLayout({ bindGroupLayouts: [uniformLayout] });

    this.uniformBuffer = device.createBuffer({
      size: 256, // 3*mat4(192) + vec4(16) padded
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });
    const bg = device.createBindGroup({
      layout: uniformLayout,
      entries: [{ binding: 0, resource: { buffer: this.uniformBuffer } }],
    });
    this.sphereBindGroup = bg;
    this.cylinderBindGroup = bg;
    this.cellBindGroup = bg;

    const depthStencil: GPUDepthStencilState = {
      depthWriteEnabled: true,
      depthCompare: "less",
      format: "depth24plus",
    };

    const sphereMod = device.createShaderModule({ code: SPHERE_WGSL });
    this.spherePipeline = device.createRenderPipeline({
      layout: pipelineLayout,
      vertex: {
        module: sphereMod,
        entryPoint: "vs_main",
        buffers: [
          {
            arrayStride: 32,
            stepMode: "instance",
            attributes: [
              { shaderLocation: 0, offset: 0, format: "float32x4" },
              { shaderLocation: 1, offset: 16, format: "float32x4" },
            ],
          },
        ],
      },
      fragment: {
        module: sphereMod,
        entryPoint: "fs_main",
        targets: [{ format: this.format }],
      },
      primitive: { topology: "triangle-strip" },
      depthStencil,
    });

    const cylMod = device.createShaderModule({ code: CYLINDER_WGSL });
    this.cylinderPipeline = device.createRenderPipeline({
      layout: pipelineLayout,
      vertex: {
        module: cylMod,
        entryPoint: "vs_main",
        buffers: [
          {
            arrayStride: 64,
            stepMode: "instance",
            attributes: [
              { shaderLocation: 0, offset: 0, format: "float32x4" },
              { shaderLocation: 1, offset: 16, format: "float32x4" },
              { shaderLocation: 2, offset: 32, format: "float32x4" },
              { shaderLocation: 3, offset: 48, format: "float32x4" },
            ],
          },
        ],
      },
      fragment: {
        module: cylMod,
        entryPoint: "fs_main",
        targets: [{ format: this.format }],
      },
      primitive: { topology: "triangle-strip" },
      depthStencil,
    });

    const cellMod = device.createShaderModule({ code: CELL_LINE_WGSL });
    this.cellPipeline = device.createRenderPipeline({
      layout: pipelineLayout,
      vertex: {
        module: cellMod,
        entryPoint: "vs_main",
        buffers: [{ arrayStride: 12, stepMode: "vertex", attributes: [{ shaderLocation: 0, offset: 0, format: "float32x3" }] }],
      },
      fragment: {
        module: cellMod,
        entryPoint: "fs_main",
        targets: [{ format: this.format }],
      },
      primitive: { topology: "line-list" },
      depthStencil,
    });
  }

  setMolecule(data: BinaryMoleculeData, fitCam = true) {
    this.data = data;
    this.selectedIndices.clear();
    if (fitCam) {
      this.camera.fit(data.center, data.boundingRadius);
    }
    this.rebuildBuffers();
  }

  setStyle(opts: {
    mode?: RepresentationMode;
    atomScale?: number;
    bondScale?: number;
    showHydrogens?: boolean;
    showCell?: boolean;
    darkBg?: boolean;
  }) {
    if (opts.mode !== undefined) this.mode = opts.mode;
    if (opts.atomScale !== undefined) this.atomScale = opts.atomScale;
    if (opts.bondScale !== undefined) this.bondScale = opts.bondScale;
    if (opts.showHydrogens !== undefined) this.showHydrogens = opts.showHydrogens;
    if (opts.showCell !== undefined) this.showCell = opts.showCell;
    if (opts.darkBg !== undefined) this.darkBg = opts.darkBg;
    this.rebuildBuffers();
  }

  setSelection(indices: number[]) {
    this.selectedIndices = new Set(indices);
    this.rebuildBuffers();
  }

  pickAt(clientX: number, clientY: number): number {
    if (!this.data) return -1;
    const rect = this.canvas.getBoundingClientRect();
    const nx = ((clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1;
    const ny = -(((clientY - rect.top) / Math.max(1, rect.height)) * 2 - 1);
    const ray = this.camera.pickRay(nx, ny, rect.width / Math.max(1, rect.height));
    return rayPickAtom(ray.origin, ray.dir, this.data.coords, this.effectiveRadii, this.data.numAtoms);
  }

  private getBondRadius(): number {
    if (this.mode === "cpk") return 0.0;
    if (this.mode === "stick") return 0.165 * this.bondScale;
    if (this.mode === "wireframe") return 0.032 * this.bondScale;
    return 0.088 * this.bondScale;
  }

  private rebuildBuffers() {
    if (!this.data) {
      this.atomCount = 0;
      this.bondCount = 0;
      this.cellVertCount = 0;
      this.dirty = true;
      return;
    }
    const t0 = performance.now();
    const { numAtoms, numBonds, coords, atomicNumbers, vdwRadii, atomRgba, bondPairs, hasCell, boxOrigin, cellMatrix } =
      this.data;

    // 1. Pack atom instances (8 floats = 32 bytes per atom)
    this.effectiveRadii = new Float32Array(numAtoms);
    const atomData = new Float32Array(numAtoms * 8);
    const massive = numAtoms > 2500;
    for (let i = 0; i < numAtoms; i++) {
      const z = atomicNumbers[i];
      let r = 0;
      if (this.showHydrogens || z !== 1) {
        if (this.mode === "cpk") {
          r = vdwRadii[i] * this.atomScale;
        } else if (this.mode === "stick") {
          r = 0.165 * this.bondScale;
        } else if (this.mode === "wireframe") {
          r = massive ? 0.0 : vdwRadii[i] * 0.04 * this.atomScale;
        } else {
          r = vdwRadii[i] * 0.25 * this.atomScale;
        }
      }
      this.effectiveRadii[i] = r;
      const base = i * 8;
      atomData[base] = coords[i * 3];
      atomData[base + 1] = coords[i * 3 + 1];
      atomData[base + 2] = coords[i * 3 + 2];
      atomData[base + 3] = r;
      atomData[base + 4] = atomRgba[i * 4] / 255;
      atomData[base + 5] = atomRgba[i * 4 + 1] / 255;
      atomData[base + 6] = atomRgba[i * 4 + 2] / 255;
      atomData[base + 7] = this.selectedIndices.has(i) ? 2.0 : atomRgba[i * 4 + 3] / 255;
    }

    // 2. Pack bond instances (16 floats = 64 bytes per bond) when visible
    const showBonds = this.mode !== "cpk" && numBonds > 0;
    let validBonds = 0;
    let bondData: Float32Array | null = null;
    if (showBonds) {
      bondData = new Float32Array(numBonds * 16);
      for (let b = 0; b < numBonds; b++) {
        const i = bondPairs[b * 2];
        const j = bondPairs[b * 2 + 1];
        if (!this.showHydrogens && (atomicNumbers[i] === 1 || atomicNumbers[j] === 1)) continue;
        const base = validBonds * 16;
        bondData[base] = coords[i * 3];
        bondData[base + 1] = coords[i * 3 + 1];
        bondData[base + 2] = coords[i * 3 + 2];
        bondData[base + 3] = 0;
        bondData[base + 4] = coords[j * 3];
        bondData[base + 5] = coords[j * 3 + 1];
        bondData[base + 6] = coords[j * 3 + 2];
        bondData[base + 7] = 0;
        bondData[base + 8] = atomRgba[i * 4] / 255;
        bondData[base + 9] = atomRgba[i * 4 + 1] / 255;
        bondData[base + 10] = atomRgba[i * 4 + 2] / 255;
        bondData[base + 11] = 1;
        bondData[base + 12] = atomRgba[j * 4] / 255;
        bondData[base + 13] = atomRgba[j * 4 + 1] / 255;
        bondData[base + 14] = atomRgba[j * 4 + 2] / 255;
        bondData[base + 15] = 1;
        validBonds++;
      }
    }

    // 3. Unit cell 12 edges (24 vertices * 3 floats)
    let cellVerts: Float32Array | null = null;
    if (this.showCell && hasCell && boxOrigin && cellMatrix) {
      const ox = boxOrigin[0],
        oy = boxOrigin[1],
        oz = boxOrigin[2];
      const corners: [number, number, number][] = [];
      for (let m = 0; m < 8; m++) {
        const a = m & 1 ? 1 : 0;
        const b = m & 2 ? 1 : 0;
        const c = m & 4 ? 1 : 0;
        corners.push([
          ox + a * cellMatrix[0] + b * cellMatrix[3] + c * cellMatrix[6],
          oy + a * cellMatrix[1] + b * cellMatrix[4] + c * cellMatrix[7],
          oz + a * cellMatrix[2] + b * cellMatrix[5] + c * cellMatrix[8],
        ]);
      }
      const edges = [
        [0, 1], [0, 2], [0, 4], [1, 3], [1, 5], [2, 3],
        [2, 6], [3, 7], [4, 5], [4, 6], [5, 7], [6, 7],
      ];
      cellVerts = new Float32Array(24 * 3);
      edges.forEach(([u, v], idx) => {
        cellVerts![idx * 6] = corners[u][0];
        cellVerts![idx * 6 + 1] = corners[u][1];
        cellVerts![idx * 6 + 2] = corners[u][2];
        cellVerts![idx * 6 + 3] = corners[v][0];
        cellVerts![idx * 6 + 4] = corners[v][1];
        cellVerts![idx * 6 + 5] = corners[v][2];
      });
    }

    if (this.device) {
      this.atomBuffer?.destroy();
      this.atomBuffer = this.device.createBuffer({
        size: Math.max(32, atomData.byteLength),
        usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
      });
      if (numAtoms > 0) this.device.queue.writeBuffer(this.atomBuffer, 0, atomData);
      this.atomCount = numAtoms;

      this.bondBuffer?.destroy();
      if (validBonds > 0 && bondData) {
        const slice = bondData.subarray(0, validBonds * 16);
        this.bondBuffer = this.device.createBuffer({
          size: Math.max(64, slice.byteLength),
          usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
        });
        this.device.queue.writeBuffer(this.bondBuffer, 0, slice);
      } else {
        this.bondBuffer = null;
      }
      this.bondCount = validBonds;

      this.cellBuffer?.destroy();
      if (cellVerts) {
        this.cellBuffer = this.device.createBuffer({
          size: cellVerts.byteLength,
          usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
        });
        this.device.queue.writeBuffer(this.cellBuffer, 0, cellVerts);
        this.cellVertCount = 24;
      } else {
        this.cellBuffer = null;
        this.cellVertCount = 0;
      }
    }

    this.telemetry.uploadMs = Number((performance.now() - t0).toFixed(1));
    this.onTelemetry?.({ ...this.telemetry });
    this.dirty = true;
  }

  public requestRedraw() {
    this.dirty = true;
  }

  private ensureDepth(w: number, h: number) {
    if (!this.device) return;
    if (this.depthTexture && this.depthTexture.width === w && this.depthTexture.height === h) return;
    this.depthTexture?.destroy();
    this.depthTexture = this.device.createTexture({
      size: [w, h],
      format: "depth24plus",
      usage: GPUTextureUsage.RENDER_ATTACHMENT,
    });
  }

  private startLoop() {
    const tick = () => {
      if (this.destroyed) return;
      this.renderFrame();
      this.rafId = requestAnimationFrame(tick);
    };
    this.rafId = requestAnimationFrame(tick);
  }

  private renderFrame() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(2, Math.floor(this.canvas.clientWidth * dpr));
    const h = Math.max(2, Math.floor(this.canvas.clientHeight * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
      this.dirty = true;
    }
    if (!this.dirty) return;
    this.dirty = false;

    const t0 = performance.now();
    if (this.device && this.gpuCtx && this.uniformBuffer) {
      this.ensureDepth(w, h);
      const view = this.camera.viewMatrix();
      const proj = this.camera.projMatrix(w / Math.max(1, h));
      const boundR = this.data?.boundingRadius ?? 8.0;
      const fogNear = Math.max(1.0, this.camera.distance - boundR * 0.2);
      const fogSpan = Math.max(6.0, boundR * 2.3);
      const minAtomPx = (this.mode === "wireframe" ? 0.0 : 1.75) * dpr;
      const minBondPx = (this.mode === "wireframe" ? 1.25 : this.mode === "stick" ? 2.1 : 1.45) * dpr;

      const u = new Float32Array(64);
      u.set(view, 0);
      u.set(proj, 16);
      u.set([fogNear, fogSpan, this.darkBg ? 1 : 0, this.getBondRadius()], 32);
      u.set([w, h, minAtomPx, minBondPx], 36);
      this.device.queue.writeBuffer(this.uniformBuffer, 0, u);

      const encoder = this.device.createCommandEncoder();
      const clearColor = this.darkBg ? { r: 0.028, g: 0.044, b: 0.068, a: 1 } : { r: 0.94, g: 0.96, b: 0.98, a: 1 };
      const pass = encoder.beginRenderPass({
        colorAttachments: [{ view: this.gpuCtx.getCurrentTexture().createView(), clearValue: clearColor, loadOp: "clear", storeOp: "store" }],
        depthStencilAttachment: {
          view: this.depthTexture!.createView(),
          depthClearValue: 1.0,
          depthLoadOp: "clear",
          depthStoreOp: "store",
        },
      });

      if (this.atomCount > 0 && this.atomBuffer && this.spherePipeline && this.sphereBindGroup) {
        pass.setPipeline(this.spherePipeline);
        pass.setBindGroup(0, this.sphereBindGroup);
        pass.setVertexBuffer(0, this.atomBuffer);
        pass.draw(4, this.atomCount);
      }
      if (this.bondCount > 0 && this.bondBuffer && this.cylinderPipeline && this.cylinderBindGroup) {
        pass.setPipeline(this.cylinderPipeline);
        pass.setBindGroup(0, this.cylinderBindGroup);
        pass.setVertexBuffer(0, this.bondBuffer);
        pass.draw(4, this.bondCount);
      }
      if (this.cellVertCount > 0 && this.cellBuffer && this.cellPipeline && this.cellBindGroup) {
        pass.setPipeline(this.cellPipeline);
        pass.setBindGroup(0, this.cellBindGroup);
        pass.setVertexBuffer(0, this.cellBuffer);
        pass.draw(this.cellVertCount);
      }
      pass.end();
      this.device.queue.submit([encoder.finish()]);
    } else if (this.ctx2d && this.data) {
      this.renderCanvas2DFallback(w, h);
    }

    const frameDt = Math.max(0.5, performance.now() - t0);
    this.frameCounter++;
    const now = performance.now();
    const dt = now - this.lastFpsStamp;
    if (dt >= 500) {
      this.telemetry.drawMs = Number(frameDt.toFixed(2));
      this.telemetry.fps = Math.min(60, Math.round(1000 / Math.max(16.6, frameDt)));
      this.frameCounter = 0;
      this.lastFpsStamp = now;
      this.onTelemetry?.({ ...this.telemetry });
    }
  }

  private renderCanvas2DFallback(w: number, h: number) {
    const ctx = this.ctx2d!;
    ctx.clearRect(0, 0, w, h);
    if (!this.data) return;
    const { numAtoms, coords, atomRgba, bondPairs, numBonds } = this.data;
    const view = this.camera.viewMatrix();
    const proj = this.camera.projMatrix(w / Math.max(1, h));
    const step = numAtoms > 8000 ? Math.ceil(numAtoms / 8000) : 1;

    const project = (x: number, y: number, z: number): [number, number, number] => {
      const vx = view[0] * x + view[4] * y + view[8] * z + view[12];
      const vy = view[1] * x + view[5] * y + view[9] * z + view[13];
      const vz = view[2] * x + view[6] * y + view[10] * z + view[14];
      const cw = -vz || 1;
      const sx = ((proj[0] * vx) / cw + 1) * 0.5 * w;
      const sy = (1 - (proj[5] * vy) / cw) * 0.5 * h;
      return [sx, sy, vz];
    };

    if (this.mode !== "cpk" && numBonds <= 6000) {
      ctx.lineWidth = this.mode === "stick" ? 5 : this.mode === "wireframe" ? 1.4 : 2.8;
      ctx.strokeStyle = this.darkBg ? "rgba(186,210,232,0.72)" : "rgba(71,85,105,0.75)";
      ctx.beginPath();
      for (let b = 0; b < numBonds; b++) {
        const i = bondPairs[b * 2],
          j = bondPairs[b * 2 + 1];
        const [x1, y1] = project(coords[i * 3], coords[i * 3 + 1], coords[i * 3 + 2]);
        const [x2, y2] = project(coords[j * 3], coords[j * 3 + 1], coords[j * 3 + 2]);
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
      }
      ctx.stroke();
    }

    for (let i = 0; i < numAtoms; i += step) {
      const r = this.effectiveRadii[i];
      if (r <= 0.001) continue;
      const [sx, sy, vz] = project(coords[i * 3], coords[i * 3 + 1], coords[i * 3 + 2]);
      const px = Math.max(1.5, (r * h) / Math.max(2, -vz * 0.72));
      ctx.fillStyle = `rgb(${atomRgba[i * 4]},${atomRgba[i * 4 + 1]},${atomRgba[i * 4 + 2]})`;
      ctx.beginPath();
      ctx.arc(sx, sy, px, 0, Math.PI * 2);
      ctx.fill();
      if (this.selectedIndices.has(i)) {
        ctx.strokeStyle = "#5eead4";
        ctx.lineWidth = 2.5;
        ctx.stroke();
      }
    }
  }

  destroy() {
    this.destroyed = true;
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.atomBuffer?.destroy();
    this.bondBuffer?.destroy();
    this.cellBuffer?.destroy();
    this.uniformBuffer?.destroy();
    this.depthTexture?.destroy();
  }
}
