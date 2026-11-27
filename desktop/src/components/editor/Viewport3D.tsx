import React, { useEffect, useRef, useState } from "react";
import { Box, Crosshair, Eye, EyeOff, Maximize2 } from "lucide-react";
import { WebGPUMolEngine, type EngineTelemetry } from "../../engine/WebGPUMolEngine";
import type { BinaryMoleculeData, RepresentationMode } from "../../types/studio";

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
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const engineRef = useRef<WebGPUMolEngine | null>(null);
  const pointerDownPos = useRef<{ x: number; y: number } | null>(null);
  const dragMode = useRef<"orbit" | "pan" | null>(null);

  const [telemetry, setTelemetry] = useState<EngineTelemetry>({
    backend: "WebGPU",
    gpuName: "Detecting GPU...",
    fps: 60,
    uploadMs: 0,
    drawMs: 0,
  });

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
    if (!data) return;
    engineRef.current?.setMolecule(data, true);
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
    }
  }, [fitNonce, data]);

  return (
    <div
      className="relative h-full w-full overflow-hidden"
      style={{ backgroundColor: darkTheme ? "#0B1220" : "#F5F7FA" }}
    >
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
            }}
            className="h-6 px-1.5 rounded text-[10.5px] hover:text-[var(--accent-primary)] cursor-pointer"
            title="侧视投影 (Side View, 沿X轴侧视)"
          >
            侧视
          </button>
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
