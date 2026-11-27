import React, { useEffect, useRef, useState } from "react";
import { Box, Camera, Crosshair, Download, Eye, EyeOff, Layers, Maximize2, Tag } from "lucide-react";
import { WebGPUMolEngine, type EngineTelemetry } from "../../engine/WebGPUMolEngine";
import type { Mat3, ScientificCameraPreset } from "../../engine/camera";
import {
  buildEspSurfaceMesh,
  buildOrbitalSurfaceMeshes,
  parseGaussianCube,
  type GaussianCubeData,
  type SurfaceColormap,
} from "../../engine/cubeIsosurface";
import { molApi } from "../../services/api";
import type { BinaryMoleculeData, RepresentationMode } from "../../types/studio";
import {
  AnnotationOverlaySvg,
  DualUnitColorBarSvg,
  composeHighResPublicationPng,
  type ShortContactOverlayItem,
  type TorsionOverlayItem,
} from "./ScientificOverlay";

interface Props {
  data: BinaryMoleculeData | null;
  reprMode: RepresentationMode;
  onChangeRepr: (m: RepresentationMode) => void;
  atomScale: number;
  onChangeAtomScale: (v: number) => void;
  bondScale: number;
  onChangeBondScale: (v: number) => void;
  showHydrogens: boolean;
  onToggleHydrogens: () => void;
  showCell: boolean;
  onToggleCell: () => void;
  showAxes: boolean;
  onToggleAxes: () => void;
  darkTheme: boolean;
  selectedIndices: number[];
  onSelectIndices: (indices: number[]) => void;
  fitNonce: number;
  onFitCamera: () => void;
}

const REPR_OPTIONS: Array<{ id: RepresentationMode; label: string }> = [
  { id: "ball_stick", label: "球棍" },
  { id: "cpk", label: "CPK" },
  { id: "stick", label: "棍状" },
  { id: "wireframe", label: "线框" },
];

const SCIENTIFIC_PRESETS: Array<{ id: ScientificCameraPreset; label: string; title: string }> = [
  { id: "vertical_front", label: "竖正", title: "Core-First 竖版正视 (LMO / ESP 对比)" },
  { id: "horizontal_front", label: "横正", title: "Core-First 横版正视" },
  { id: "side_edge", label: "侧缘", title: "Core-First 侧视 (扭转角 / 层间距)" },
  { id: "paper_oblique", label: "论文斜", title: "文献 Figure 斜俯视 (-35° / +12° + 88% 自动取景)" },
];

export const Viewport3D: React.FC<Props> = ({
  data,
  reprMode,
  onChangeRepr,
  atomScale,
  onChangeAtomScale,
  bondScale,
  onChangeBondScale,
  showHydrogens,
  onToggleHydrogens,
  showCell,
  onToggleCell,
  showAxes,
  onToggleAxes,
  darkTheme,
  selectedIndices,
  onSelectIndices,
  fitNonce,
  onFitCamera,
}) => {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const engineRef = useRef<WebGPUMolEngine | null>(null);
  const overlaySvgRef = useRef<SVGSVGElement | null>(null);
  const colorBarSvgRef = useRef<SVGSVGElement | null>(null);
  const pointerDownPos = useRef<{ x: number; y: number } | null>(null);
  const dragMode = useRef<"orbit" | "pan" | null>(null);

  const [telemetry, setTelemetry] = useState<EngineTelemetry>({
    backend: "WebGPU",
    gpuName: "Detecting GPU...",
    fps: 60,
    uploadMs: 0,
    drawMs: 0,
  });

  const [viewSize, setViewSize] = useState({ w: 800, h: 600 });
  const [camNonce, setCamNonce] = useState(0);
  const [showSurfacePopover, setShowSurfacePopover] = useState(false);

  // Module 3 state: Isosurfaces, absolute ColorBar & SVG annotations
  const [moCube, setMoCube] = useState<GaussianCubeData | null>(null);
  const [densCube, setDensCube] = useState<GaussianCubeData | null>(null);
  const [espCube, setEspCube] = useState<GaussianCubeData | null>(null);
  const [surfaceKind, setSurfaceKind] = useState<"none" | "mo" | "esp">("none");
  const [isoValue, setIsoValue] = useState(0.03);
  const [espIsoDensity, setEspIsoDensity] = useState(0.001);
  const [espMinAu, setEspMinAu] = useState(-0.042);
  const [espMaxAu, setEspMaxAu] = useState(0.028);
  const [colormap, setColormap] = useState<SurfaceColormap>("BWR");
  const [surfaceOpacity, setSurfaceOpacity] = useState(0.75);
  const [colorBarOrient, setColorBarOrient] = useState<"vertical" | "horizontal">("vertical");
  const [showColorBar, setShowColorBar] = useState(false);

  const [showAnnotations, setShowAnnotations] = useState(false);
  const [torsions, setTorsions] = useState<TorsionOverlayItem[]>([]);
  const [shortContacts, setShortContacts] = useState<ShortContactOverlayItem[]>([]);
  const [transparentExport, setTransparentExport] = useState(true);
  const [exportStatus, setExportStatus] = useState("");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const engine = new WebGPUMolEngine(canvas, (t) => setTelemetry(t));
    engineRef.current = engine;
    void engine.init();
    return () => {
      engine.destroy();
      engineRef.current = null;
    };
  }, []);

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        setViewSize({
          w: Math.max(100, Math.round(e.contentRect.width)),
          h: Math.max(100, Math.round(e.contentRect.height)),
        });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!data) return;
    engineRef.current?.setMolecule(data, true);
    setCamNonce((n) => n + 1);
  }, [data]);

  useEffect(() => {
    engineRef.current?.setStyle({
      mode: reprMode,
      atomScale,
      bondScale,
      showHydrogens,
      showCell,
      darkBg: darkTheme,
    });
  }, [reprMode, atomScale, bondScale, showHydrogens, showCell, darkTheme]);

  useEffect(() => {
    engineRef.current?.setSelection(selectedIndices);
  }, [selectedIndices]);

  useEffect(() => {
    if (fitNonce > 0 && data && engineRef.current) {
      engineRef.current.camera.fit(data.center, data.boundingRadius);
      engineRef.current.requestRedraw();
      setCamNonce((n) => n + 1);
    }
  }, [fitNonce, data]);

  // Rebuild WebGPU isosurface meshes whenever cube parameters change
  useEffect(() => {
    const eng = engineRef.current;
    if (!eng) return;
    if (surfaceKind === "mo" && moCube) {
      const meshes = buildOrbitalSurfaceMeshes(moCube, isoValue, surfaceOpacity);
      eng.setSurfaceMeshes(meshes);
      eng.requestRedraw();
    } else if (surfaceKind === "esp" && densCube && espCube) {
      const mesh = buildEspSurfaceMesh(
        densCube,
        espCube,
        espIsoDensity,
        espMinAu,
        espMaxAu,
        colormap,
        surfaceOpacity
      );
      eng.setSurfaceMeshes([mesh]);
      setShowColorBar(true);
      eng.requestRedraw();
    } else {
      eng.clearSurfaces();
      eng.requestRedraw();
    }
  }, [
    surfaceKind,
    moCube,
    densCube,
    espCube,
    isoValue,
    espIsoDensity,
    espMinAu,
    espMaxAu,
    colormap,
    surfaceOpacity,
  ]);

  const applyScientificPreset = async (preset: ScientificCameraPreset) => {
    const eng = engineRef.current;
    if (!eng || !data) return;
    let rCan: Mat3 | undefined;
    try {
      const res = await molApi.orientMolecule(false);
      if (res.ok && res.orientation?.rotation_3x3) {
        rCan = res.orientation.rotation_3x3;
      }
    } catch {
      // Fallback cleanly to local TS heavy-atom PCA
    }
    const w = Math.max(200, canvasRef.current?.clientWidth || viewSize.w);
    const h = Math.max(200, canvasRef.current?.clientHeight || viewSize.h);
    eng.camera.applyScientificPreset(
      preset,
      data.coords,
      data.numAtoms,
      w,
      h,
      rCan,
      data.atomicNumbers,
      eng.getSurfaceWorldPoints(),
      0.88
    );
    eng.requestRedraw();
    setCamNonce((n) => n + 1);
  };

  const toggleAnnotations = async () => {
    if (showAnnotations) {
      setShowAnnotations(false);
      return;
    }
    try {
      const res = await molApi.runAnalysis("PROP-TORSION");
      const m = (res.result?.metrics ?? {}) as Record<string, unknown>;
      setTorsions(Array.isArray(m.torsions) ? (m.torsions as TorsionOverlayItem[]) : []);
      setShortContacts(
        Array.isArray(m.short_contacts) ? (m.short_contacts as ShortContactOverlayItem[]) : []
      );
      setShowAnnotations(true);
    } catch (err) {
      setExportStatus(`二面角标注提取失败: ${String(err)}`);
    }
  };

  const handleLoadCubeFile = async (role: "mo" | "density" | "esp") => {
    try {
      let text = "";
      if (window.molforgeDesktop) {
        const dlg = await window.molforgeDesktop.dialogs.openQcLogFile();
        if (dlg.cancelled || !dlg.filePath) return;
        const readRes = await window.molforgeDesktop.files.readText(dlg.filePath);
        text = readRes.content;
      } else {
        const inp = document.createElement("input");
        inp.type = "file";
        inp.accept = ".cub,.cube";
        text = await new Promise<string>((resolve, reject) => {
          inp.onchange = () => {
            const f = inp.files?.[0];
            if (!f) reject(new Error("cancelled"));
            else void f.text().then(resolve, reject);
          };
          inp.click();
        });
      }
      const parsed = parseGaussianCube(text);
      if (role === "mo") {
        setMoCube(parsed);
        setSurfaceKind("mo");
        setExportStatus(`已加载轨道网格 ${parsed.dims.join("×")}`);
      } else if (role === "density") {
        setDensCube(parsed);
        if (espCube) setSurfaceKind("esp");
        setExportStatus(`已加载密度网格 ${parsed.dims.join("×")}`);
      } else {
        setEspCube(parsed);
        if (densCube) setSurfaceKind("esp");
        setShowColorBar(true);
        setExportStatus(`已加载 ESP 网格 ${parsed.dims.join("×")}`);
      }
    } catch (err) {
      if (String(err) !== "Error: cancelled") {
        setExportStatus(`加载 .cub 失败: ${String(err)}`);
      }
    }
  };

  const handleExportHdPng = async () => {
    const eng = engineRef.current;
    if (!eng) return;
    try {
      const hdCanvas = await eng.renderHighResCanvas(3, transparentExport);
      const dataUrl = await composeHighResPublicationPng(
        hdCanvas,
        showAnnotations ? overlaySvgRef.current : null,
        showColorBar ? colorBarSvgRef.current : null,
        darkTheme,
        transparentExport
      );
      const base64 = dataUrl.split(",")[1] || "";
      if (window.molforgeDesktop) {
        const dlg = await window.molforgeDesktop.dialogs.saveFile("molforge_figure_300dpi.png", [
          { name: "PNG 高清图像 (*.png)", extensions: ["png"] },
        ]);
        if (dlg.cancelled || !dlg.filePath) return;
        await window.molforgeDesktop.files.writeBase64Atomic(dlg.filePath, base64);
        setExportStatus(`已导出高清 PNG (${hdCanvas.width}×${hdCanvas.height})`);
      } else {
        const a = document.createElement("a");
        a.href = dataUrl;
        a.download = "molforge_figure_300dpi.png";
        a.click();
        setExportStatus(`已下载高清 PNG (${hdCanvas.width}×${hdCanvas.height})`);
      }
    } catch (err) {
      setExportStatus(`导出 PNG 失败: ${String(err)}`);
    }
  };

  const handleExportColorBarSvg = async () => {
    const targetSvg = colorBarSvgRef.current || overlaySvgRef.current;
    if (!targetSvg) {
      setExportStatus("请先开启双单位颜色棒或标注叠加层");
      return;
    }
    const xml = new XMLSerializer().serializeToString(targetSvg);
    try {
      if (window.molforgeDesktop) {
        const dlg = await window.molforgeDesktop.dialogs.saveFile("molforge_colorbar.svg", [
          { name: "矢量 SVG (*.svg)", extensions: ["svg"] },
        ]);
        if (dlg.cancelled || !dlg.filePath) return;
        await window.molforgeDesktop.files.writeTextAtomic(dlg.filePath, xml);
        setExportStatus("已导出矢量 SVG");
      } else {
        const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "molforge_colorbar.svg";
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } catch (err) {
      setExportStatus(`导出 SVG 失败: ${String(err)}`);
    }
  };

  return (
    <div
      ref={hostRef}
      className="relative h-full w-full overflow-hidden"
      style={{ backgroundColor: darkTheme ? "#0B1220" : "#F5F7FA" }}
    >
      {/* 2D Vector Projection Annotations Overlay (Module 3) */}
      {showAnnotations && engineRef.current && (
        <AnnotationOverlaySvg
          key={camNonce}
          width={viewSize.w}
          height={viewSize.h}
          camera={engineRef.current.camera}
          data={engineRef.current.getMolecule() ?? data}
          torsions={torsions}
          shortContacts={shortContacts}
          darkTheme={darkTheme}
          svgRef={overlaySvgRef}
        />
      )}

      {/* Dual-Unit Vector ColorBar Overlay (Module 3) */}
      {showColorBar && (
        <div
          className="absolute top-12 right-3 z-10 p-2 rounded-lg backdrop-blur-md pointer-events-auto"
          style={{
            backgroundColor: darkTheme ? "rgba(15, 23, 42, 0.78)" : "rgba(255, 255, 255, 0.85)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <DualUnitColorBarSvg
            minAu={espMinAu}
            maxAu={espMaxAu}
            palette={colormap}
            orientation={colorBarOrient}
            darkTheme={darkTheme}
            svgRef={colorBarSvgRef}
          />
        </div>
      )}

      {/* Surface & Publication Export Popover */}
      {showSurfacePopover && (
        <div
          className="absolute bottom-24 right-3 z-20 w-80 p-3 rounded-xl space-y-2.5 text-[11px] backdrop-blur-xl"
          style={{
            backgroundColor: "var(--bg-secondary)",
            border: "1px solid var(--border-subtle)",
            boxShadow: "var(--shadow-panel)",
          }}
        >
          <div className="flex items-center justify-between font-semibold">
            <span>等值面、双单位色标与高清出图</span>
            <button
              type="button"
              onClick={() => setShowSurfacePopover(false)}
              className="text-[11px] cursor-pointer"
              style={{ color: "var(--text-muted)" }}
            >
              关闭
            </button>
          </div>

          <div className="grid grid-cols-3 gap-1.5">
            <button type="button" onClick={() => void handleLoadCubeFile("mo")} className="studio-btn !h-7 !text-[10.5px]">
              加载 MO .cub
            </button>
            <button type="button" onClick={() => void handleLoadCubeFile("density")} className="studio-btn !h-7 !text-[10.5px]">
              密度 .cub
            </button>
            <button type="button" onClick={() => void handleLoadCubeFile("esp")} className="studio-btn !h-7 !text-[10.5px]">
              ESP .cub
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-0.5">
              <span style={{ color: "var(--text-muted)" }}>显示模式</span>
              <select
                value={surfaceKind}
                onChange={(e) => setSurfaceKind(e.target.value as "none" | "mo" | "esp")}
                className="studio-input w-full !h-7 !text-[11px]"
              >
                <option value="none">关闭等值面</option>
                <option value="mo" disabled={!moCube}>MO 正负相 (绿/蓝)</option>
                <option value="esp" disabled={!densCube || !espCube}>ESP 映射密度表面</option>
              </select>
            </label>
            <label className="space-y-0.5">
              <span style={{ color: "var(--text-muted)" }}>绝对色标方法</span>
              <select
                value={colormap}
                onChange={(e) => setColormap(e.target.value as SurfaceColormap)}
                className="studio-input w-full !h-7 !text-[11px]"
              >
                <option value="BWR">BWR (蓝-白-红)</option>
                <option value="RWB">RWB (红-白-蓝)</option>
                <option value="Viridis">Viridis</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-3 gap-1.5">
            <label className="space-y-0.5">
              <span style={{ color: "var(--text-muted)" }}>Min (a.u.)</span>
              <input
                type="number"
                step={0.005}
                value={espMinAu}
                onChange={(e) => setEspMinAu(Number(e.target.value))}
                className="studio-input w-full !h-7 !text-[11px] mono-num"
              />
            </label>
            <label className="space-y-0.5">
              <span style={{ color: "var(--text-muted)" }}>Max (a.u.)</span>
              <input
                type="number"
                step={0.005}
                value={espMaxAu}
                onChange={(e) => setEspMaxAu(Number(e.target.value))}
                className="studio-input w-full !h-7 !text-[11px] mono-num"
              />
            </label>
            <label className="space-y-0.5">
              <span style={{ color: "var(--text-muted)" }}>{surfaceKind === "esp" ? "ρ 阈值" : "MO 阈值"}</span>
              <input
                type="number"
                step={surfaceKind === "esp" ? 0.0005 : 0.005}
                value={surfaceKind === "esp" ? espIsoDensity : isoValue}
                onChange={(e) =>
                  surfaceKind === "esp"
                    ? setEspIsoDensity(Number(e.target.value))
                    : setIsoValue(Number(e.target.value))
                }
                className="studio-input w-full !h-7 !text-[11px] mono-num"
              />
            </label>
          </div>

          <div className="flex items-center justify-between gap-2">
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={showColorBar}
                onChange={(e) => setShowColorBar(e.target.checked)}
              />
              <span>双单位 ColorBar</span>
            </label>
            <select
              value={colorBarOrient}
              onChange={(e) => setColorBarOrient(e.target.value as "vertical" | "horizontal")}
              className="studio-input !h-6 !text-[10.5px]"
            >
              <option value="vertical">竖版</option>
              <option value="horizontal">横版</option>
            </select>
            <label className="flex items-center gap-1">
              <span>透明</span>
              <input
                type="range"
                min={0.25}
                max={1.0}
                step={0.05}
                value={surfaceOpacity}
                onChange={(e) => setSurfaceOpacity(Number(e.target.value))}
                className="w-12"
              />
            </label>
          </div>

          <div className="flex items-center justify-between gap-2 pt-1 border-t border-[var(--border-subtle)]">
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={transparentExport}
                onChange={(e) => setTransparentExport(e.target.checked)}
              />
              <span>透明底导出</span>
            </label>
            <div className="flex items-center gap-1">
              <button type="button" onClick={() => void handleExportColorBarSvg()} className="studio-btn !h-7 !px-2">
                <Download size={11} />
                <span>SVG</span>
              </button>
              <button type="button" onClick={() => void handleExportHdPng()} className="studio-btn studio-btn-primary !h-7 !px-2">
                <Camera size={11} />
                <span>高清 PNG</span>
              </button>
            </div>
          </div>
          {exportStatus && (
            <div className="text-[10.5px]" style={{ color: "var(--accent-primary)" }}>
              {exportStatus}
            </div>
          )}
        </div>
      )}

      {/* 3D Status & Fit Pill (Bottom-Right to keep top viewport completely clean) */}
      <div className="absolute bottom-14 right-3 z-10 flex items-center gap-1.5 pointer-events-none">
        <div
          className="px-2.5 py-1 rounded-md text-[11px] flex items-center gap-2 pointer-events-auto"
          style={{
            backgroundColor: "var(--bg-secondary)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-secondary)",
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor:
                telemetry.backend === "WebGPU" ? "var(--accent-primary)" : "var(--semantic-warning)",
            }}
          />
          <span className="font-medium" style={{ color: "var(--text-primary)" }}>
            {telemetry.backend}
          </span>
          <span className="hidden lg:inline truncate max-w-[180px]">{telemetry.gpuName}</span>
          <span className="mono-num" style={{ color: "var(--accent-primary)" }}>
            {telemetry.fps} FPS
          </span>
        </div>

        <button
          type="button"
          onClick={() => void toggleAnnotations()}
          className="studio-btn !h-7 !px-2 pointer-events-auto whitespace-nowrap shrink-0"
          style={showAnnotations ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
          title="3D→2D 矢量标注层 (核-翼二面角与键长)"
        >
          <Tag size={12} />
          <span>标注</span>
        </button>

        <button
          type="button"
          onClick={() => setShowSurfacePopover((v) => !v)}
          className="studio-btn !h-7 !px-2 pointer-events-auto whitespace-nowrap shrink-0"
          style={showSurfacePopover || showColorBar ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
          title="WebGPU 等值面、双单位颜色棒与 300 DPI 高清导出"
        >
          <Layers size={12} />
          <span>等值面/导出</span>
        </button>

        <button
          type="button"
          onClick={onFitCamera}
          className="studio-btn !h-7 !px-2.5 pointer-events-auto whitespace-nowrap shrink-0"
          title="重设 3D 视角并居中分子"
        >
          <Maximize2 size={12} />
          <span>视角适配</span>
        </button>
      </div>

      {/* Axes Indicator HUD */}
      {showAxes && (
        <div
          className="absolute bottom-14 left-3 z-10 pointer-events-none px-2 py-1 rounded-md text-[10px] mono-num flex items-center gap-2"
          style={{
            backgroundColor: "var(--bg-secondary)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <span style={{ color: "#E57878" }}>X</span>
          <span style={{ color: "#31B7A5" }}>Y</span>
          <span style={{ color: "#6BA9ED" }}>Z</span>
        </div>
      )}

      <canvas
        ref={canvasRef}
        data-testid="canvas-3d"
        className="w-full h-full block cursor-grab active:cursor-grabbing"
        onMouseDown={(e) => {
          pointerDownPos.current = { x: e.clientX, y: e.clientY };
          dragMode.current = e.button === 2 || e.shiftKey ? "pan" : "orbit";
        }}
        onMouseMove={(e) => {
          if (!dragMode.current || !pointerDownPos.current) return;
          const dx = e.clientX - pointerDownPos.current.x;
          const dy = e.clientY - pointerDownPos.current.y;
          pointerDownPos.current = { x: e.clientX, y: e.clientY };
          const eng = engineRef.current;
          if (!eng) return;
          if (dragMode.current === "orbit") eng.camera.orbit(dx, dy);
          else eng.camera.pan(dx, dy, Math.max(1, e.currentTarget.clientHeight));
          eng.requestRedraw();
          setCamNonce((n) => n + 1);
        }}
        onMouseUp={(e) => {
          if (dragMode.current === "orbit" && pointerDownPos.current) {
            const moved = Math.hypot(
              e.clientX - pointerDownPos.current.x,
              e.clientY - pointerDownPos.current.y
            );
            if (moved < 2.5 && engineRef.current) {
              const picked = engineRef.current.pickAt(e.clientX, e.clientY);
              if (picked >= 0) onSelectIndices([picked]);
              else onSelectIndices([]);
            }
          }
          dragMode.current = null;
          pointerDownPos.current = null;
        }}
        onMouseLeave={() => {
          dragMode.current = null;
          pointerDownPos.current = null;
        }}
        onWheel={(e) => {
          e.preventDefault();
          engineRef.current?.camera.zoom(e.deltaY);
          engineRef.current?.requestRedraw();
          setCamNonce((n) => n + 1);
        }}
        onContextMenu={(e) => e.preventDefault()}
      />

      {/* Bottom Visualization Controls */}
      <div
        className="absolute bottom-2.5 left-1/2 -translate-x-1/2 z-10 px-2 py-1.5 rounded-xl flex items-center justify-center gap-1.5 flex-wrap w-max max-w-[96%]"
        style={{
          backgroundColor: "var(--bg-secondary)",
          border: "1px solid var(--border-subtle)",
          boxShadow: "var(--shadow-panel)",
        }}
      >
        <div className="flex items-center gap-0.5 p-0.5 rounded-lg shrink-0" style={{ backgroundColor: "var(--bg-primary)" }}>
          {REPR_OPTIONS.map((opt) => {
            const active = reprMode === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => onChangeRepr(opt.id)}
                className="h-6 px-2 rounded-md text-[11px] font-medium cursor-pointer transition-colors whitespace-nowrap shrink-0"
                style={{
                  backgroundColor: active ? "var(--accent-primary)" : "transparent",
                  color: active ? "var(--accent-contrast)" : "var(--text-secondary)",
                }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        <label className="flex items-center gap-1 text-[11px] shrink-0 whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
          <span>球径</span>
          <input
            type="range"
            min={0.4}
            max={1.8}
            step={0.05}
            value={atomScale}
            onChange={(e) => onChangeAtomScale(Number(e.target.value))}
            className="w-12 accent-[var(--accent-primary)]"
          />
        </label>

        <label className="flex items-center gap-1 text-[11px] shrink-0 whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
          <span>键粗</span>
          <input
            type="range"
            min={0.4}
            max={2.2}
            step={0.05}
            value={bondScale}
            onChange={(e) => onChangeBondScale(Number(e.target.value))}
            className="w-12 accent-[var(--accent-primary)]"
          />
        </label>

        {/* Camera Views Quick Switch */}
        <div className="flex items-center gap-0.5 p-0.5 rounded-lg shrink-0 border border-[var(--border-subtle)]" style={{ backgroundColor: "var(--bg-primary)" }}>
          <button
            type="button"
            onClick={() => {
              engineRef.current?.camera.setFrontView();
              engineRef.current?.requestRedraw();
              setCamNonce((n) => n + 1);
            }}
            className="h-6 px-1.5 rounded text-[10.5px] hover:text-[var(--accent-primary)] cursor-pointer"
            title="正视投影 (Front View, Z轴向内)"
          >
            正视
          </button>
          <button
            type="button"
            onClick={() => {
              engineRef.current?.camera.setTopView();
              engineRef.current?.requestRedraw();
              setCamNonce((n) => n + 1);
            }}
            className="h-6 px-1.5 rounded text-[10.5px] hover:text-[var(--accent-primary)] cursor-pointer"
            title="俯视投影 (Top View, 沿Y轴俯视)"
          >
            俯视
          </button>
          <button
            type="button"
            onClick={() => {
              engineRef.current?.camera.setSideView();
              engineRef.current?.requestRedraw();
              setCamNonce((n) => n + 1);
            }}
            className="h-6 px-1.5 rounded text-[10.5px] hover:text-[var(--accent-primary)] cursor-pointer"
            title="侧视投影 (Side View, 沿X轴侧视)"
          >
            侧视
          </button>
          {SCIENTIFIC_PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              data-testid={`preset-${p.id}`}
              onClick={() => void applyScientificPreset(p.id)}
              className="h-6 px-1.5 rounded text-[10.5px] hover:text-[var(--accent-primary)] cursor-pointer"
              title={p.title}
            >
              {p.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={onToggleHydrogens}
          className="studio-btn !h-6 !px-1.5 text-[11px] whitespace-nowrap shrink-0"
          style={showHydrogens ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
        >
          {showHydrogens ? <Eye size={11.5} /> : <EyeOff size={11.5} />}
          <span>H</span>
        </button>

        {data?.hasCell && (
          <button
            type="button"
            onClick={onToggleCell}
            className="studio-btn !h-6 !px-1.5 text-[11px] whitespace-nowrap shrink-0"
            style={showCell ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
          >
            <Box size={11.5} />
            <span>晶胞</span>
          </button>
        )}

        <button
          type="button"
          onClick={onToggleAxes}
          className="studio-btn !h-6 !px-1.5 text-[11px] whitespace-nowrap shrink-0"
          style={showAxes ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
        >
          <Crosshair size={11.5} />
          <span>轴</span>
        </button>
      </div>
    </div>
  );
};
