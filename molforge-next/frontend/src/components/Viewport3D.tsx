import React, { useEffect, useRef, useState } from "react";
import { Box, Eye, RotateCcw, SlidersHorizontal, Sparkles } from "lucide-react";
import { WebGPUMolEngine, type EngineTelemetry } from "../engine/WebGPUMolEngine";
import type { Atom2DItem, BinaryMoleculeData, DocumentSummary, EditTool, RepresentationMode } from "../types/molforge";

interface Props {
  molecule: BinaryMoleculeData | null;
  summary: DocumentSummary | null;
  atoms2d: Atom2DItem[];
  selectedIndices: number[];
  onSelectIndices: (indices: number[]) => void;
  mode: RepresentationMode;
  onModeChange: (m: RepresentationMode) => void;
  darkTheme: boolean;
  activeTool: EditTool;
  onEraseIndex: (idx: number) => void;
  onSproutIndex: (idx: number) => void;
  onTelemetry?: (t: EngineTelemetry) => void;
}

const MODE_OPTIONS: Array<{ id: RepresentationMode; label: string }> = [
  { id: "ball_stick", label: "球棍" },
  { id: "cpk", label: "CPK" },
  { id: "stick", label: "棍状" },
  { id: "wireframe", label: "线框" },
];

export const Viewport3D: React.FC<Props> = ({
  molecule,
  summary,
  atoms2d,
  selectedIndices,
  onSelectIndices,
  mode,
  onModeChange,
  darkTheme,
  activeTool,
  onEraseIndex,
  onSproutIndex,
  onTelemetry,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const engineRef = useRef<WebGPUMolEngine | null>(null);
  const dragRef = useRef<{ active: boolean; button: number; x: number; y: number; moved: boolean }>({
    active: false,
    button: 0,
    x: 0,
    y: 0,
    moved: false,
  });

  const [atomScale, setAtomScale] = useState(1.0);
  const [bondScale, setBondScale] = useState(1.0);
  const [showH, setShowH] = useState(true);
  const [showCell, setShowCell] = useState(true);
  const [showAxes, setShowAxes] = useState(true);
  const [scaleMenuOpen, setScaleMenuOpen] = useState(false);
  const [camAngles, setCamAngles] = useState({ yaw: 0.55, pitch: 0.35 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const eng = new WebGPUMolEngine(canvas, onTelemetry);
    engineRef.current = eng;
    void eng.init();
    const ro = new ResizeObserver(() => eng.requestRedraw());
    ro.observe(canvas);
    return () => {
      ro.disconnect();
      eng.destroy();
      engineRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (molecule && engineRef.current) {
      engineRef.current.setMolecule(molecule, true);
      setCamAngles({ yaw: engineRef.current.camera.yaw, pitch: engineRef.current.camera.pitch });
    }
  }, [molecule]);

  useEffect(() => {
    engineRef.current?.setStyle({
      mode,
      atomScale,
      bondScale,
      showHydrogens: showH,
      showCell,
      darkBg: darkTheme,
    });
  }, [mode, atomScale, bondScale, showH, showCell, darkTheme]);

  useEffect(() => {
    engineRef.current?.setSelection(selectedIndices);
  }, [selectedIndices]);

  let measureText = "";
  if (molecule && selectedIndices.length === 2) {
    const [a, b] = selectedIndices;
    const dx = molecule.coords[a * 3] - molecule.coords[b * 3];
    const dy = molecule.coords[a * 3 + 1] - molecule.coords[b * 3 + 1];
    const dz = molecule.coords[a * 3 + 2] - molecule.coords[b * 3 + 2];
    const dist = Math.hypot(dx, dy, dz);
    const sa = atoms2d[a]?.symbol ?? `#${a + 1}`;
    const sb = atoms2d[b]?.symbol ?? `#${b + 1}`;
    measureText = `键长 ${sa}${a + 1}–${sb}${b + 1}: ${dist.toFixed(4)} Å`;
  } else if (molecule && selectedIndices.length === 3) {
    const [a, b, c] = selectedIndices;
    const v1 = [
      molecule.coords[a * 3] - molecule.coords[b * 3],
      molecule.coords[a * 3 + 1] - molecule.coords[b * 3 + 1],
      molecule.coords[a * 3 + 2] - molecule.coords[b * 3 + 2],
    ];
    const v2 = [
      molecule.coords[c * 3] - molecule.coords[b * 3],
      molecule.coords[c * 3 + 1] - molecule.coords[b * 3 + 1],
      molecule.coords[c * 3 + 2] - molecule.coords[b * 3 + 2],
    ];
    const n1 = Math.hypot(...v1) || 1;
    const n2 = Math.hypot(...v2) || 1;
    const dot = (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (n1 * n2);
    const angle = (Math.acos(Math.max(-1, Math.min(1, dot))) * 180) / Math.PI;
    measureText = `键角 (#${a + 1}-#${b + 1}-#${c + 1}): ${angle.toFixed(2)}°`;
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    dragRef.current = { active: true, button: e.button, x: e.clientX, y: e.clientY, moved: false };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragRef.current.active || !engineRef.current) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    if (Math.hypot(dx, dy) > 2) dragRef.current.moved = true;
    dragRef.current.x = e.clientX;
    dragRef.current.y = e.clientY;
    if (dragRef.current.button === 2 || e.altKey || e.buttons === 4) {
      engineRef.current.camera.pan(dx, dy, canvasRef.current?.clientHeight || 600);
    } else {
      engineRef.current.camera.orbit(dx, dy);
      setCamAngles({ yaw: engineRef.current.camera.yaw, pitch: engineRef.current.camera.pitch });
    }
    engineRef.current.requestRedraw();
  };

  const handleMouseUp = (e: React.MouseEvent) => {
    const wasMoved = dragRef.current.moved;
    dragRef.current.active = false;
    if (!wasMoved && e.button === 0 && engineRef.current) {
      const idx = engineRef.current.pickAt(e.clientX, e.clientY);
      if (idx >= 0) {
        if (activeTool === "erase") {
          onEraseIndex(idx);
          return;
        }
        if (activeTool === "atom") {
          onSproutIndex(idx);
          return;
        }
        if (e.shiftKey) {
          const next = selectedIndices.includes(idx)
            ? selectedIndices.filter((x) => x !== idx)
            : [...selectedIndices.slice(-2), idx];
          onSelectIndices(next);
        } else {
          onSelectIndices([idx]);
        }
      } else if (!e.shiftKey) {
        onSelectIndices([]);
      }
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    engineRef.current?.camera.zoom(e.deltaY);
    engineRef.current?.requestRedraw();
  };

  // Compute rotated 3D coordinate axes triad projection for SVG gizmo
  const cy = Math.cos(camAngles.yaw),
    sy = Math.sin(camAngles.yaw),
    cp = Math.cos(camAngles.pitch),
    sp = Math.sin(camAngles.pitch);
  const projectAxis = (vx: number, vy: number, vz: number) => {
    const x1 = vx * cy - vz * sy;
    const z1 = vx * sy + vz * cy;
    const y2 = vy * cp - z1 * sp;
    return [30 + x1 * 20, 30 - y2 * 20];
  };
  const [xx, xy] = projectAxis(1, 0, 0);
  const [yx, yy] = projectAxis(0, 1, 0);
  const [zx, zy] = projectAxis(0, 0, 1);

  return (
    <div
      className="relative flex-1 h-full overflow-hidden select-none"
      style={{ background: "var(--md-sys-color-stage-radial)" }}
    >
      <canvas
        ref={canvasRef}
        className="w-full h-full block cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onContextMenu={(e) => e.preventDefault()}
        onWheel={handleWheel}
      />

      {/* Top-Left Expressive Scientific HUD */}
      {summary && (
        <div className="absolute top-3.5 left-3.5 flex flex-col gap-1.5 pointer-events-none max-w-[calc(100%-130px)]">
          <div className="glass-pill rounded-2xl px-3.5 py-2 flex items-center gap-3">
            <div className="min-w-0">
              <div className="text-xs font-semibold tracking-tight flex items-center gap-2 flex-wrap">
                <span className="truncate">{summary.name}</span>
                <span
                  className="mono-num text-[11px] px-2 py-0.5 rounded-full shrink-0"
                  style={{
                    background: "var(--md-sys-color-primary-container)",
                    color: "var(--md-sys-color-primary)",
                  }}
                >
                  {summary.formula}
                </span>
              </div>
              <div
                className="mono-num text-[11px] mt-0.5 flex items-center gap-2 flex-wrap"
                style={{ color: "var(--md-sys-color-on-surface-muted)" }}
              >
                <span>{summary.num_atoms.toLocaleString()} atoms</span>
                <span>·</span>
                <span>{summary.num_bonds.toLocaleString()} bonds</span>
                <span>·</span>
                <span>
                  Q={summary.charge} / {summary.spin_label}
                </span>
              </div>
            </div>
          </div>

          {measureText && (
            <div
              className="glass-pill rounded-xl px-3 py-1.5 text-xs mono-num font-medium flex items-center gap-1.5 self-start"
              style={{ color: "var(--md-sys-color-primary)" }}
            >
              <Sparkles className="w-3.5 h-3.5" />
              {measureText}
            </div>
          )}
        </div>
      )}

      {/* Top-Right Quick Camera Reset */}
      <div className="absolute top-3.5 right-3.5">
        <button
          onClick={() => {
            if (molecule && engineRef.current) {
              engineRef.current.camera.fit(molecule.center, molecule.boundingRadius);
              setCamAngles({ yaw: engineRef.current.camera.yaw, pitch: engineRef.current.camera.pitch });
              engineRef.current.requestRedraw();
            }
          }}
          title="左键旋转 · 右键平移 · 滚轮缩放 · Shift+点击测距测角"
          className="glass-pill rounded-xl px-2.5 py-1.5 text-xs flex items-center gap-1.5 hover:scale-105 cursor-pointer whitespace-nowrap"
        >
          <RotateCcw className="w-3.5 h-3.5" style={{ color: "var(--md-sys-color-primary)" }} />
          <span>视角适配</span>
        </button>
      </div>

      {/* Bottom-Left Rotating 3D XYZ Axes Gizmo */}
      {showAxes && (
        <div className="absolute bottom-14 left-3 pointer-events-none opacity-85 hidden sm:block">
          <svg width={60} height={60} viewBox="0 0 60 60">
            <line x1={30} y1={30} x2={xx} y2={xy} stroke="#f87171" strokeWidth={2} strokeLinecap="round" />
            <text x={xx} y={xy} fill="#f87171" fontSize={9} fontWeight={700} dx={3} dy={3}>X</text>
            <line x1={30} y1={30} x2={yx} y2={yy} stroke="#4ade80" strokeWidth={2} strokeLinecap="round" />
            <text x={yx} y={yy} fill="#4ade80" fontSize={9} fontWeight={700} dx={3} dy={3}>Y</text>
            <line x1={30} y1={30} x2={zx} y2={zy} stroke="#60a5fa" strokeWidth={2} strokeLinecap="round" />
            <text x={zx} y={zy} fill="#60a5fa" fontSize={9} fontWeight={700} dx={3} dy={3}>Z</text>
          </svg>
        </div>
      )}

      {/* Scale Sliders Popover above bottom dock */}
      {scaleMenuOpen && (
        <div
          className="absolute bottom-16 left-1/2 -translate-x-1/2 glass-pill rounded-2xl p-3 flex flex-col gap-2 w-60 z-30"
          style={{ border: "1px solid var(--md-sys-color-outline-strong)" }}
        >
          <div className="flex items-center justify-between text-xs">
            <span>球径缩放 ({Math.round(atomScale * 100)}%)</span>
            <input
              type="range"
              min={0.4}
              max={2.2}
              step={0.05}
              value={atomScale}
              onChange={(e) => setAtomScale(parseFloat(e.target.value))}
              className="w-28 accent-[#5eead4] cursor-pointer"
            />
          </div>
          <div className="flex items-center justify-between text-xs">
            <span>键粗缩放 ({Math.round(bondScale * 100)}%)</span>
            <input
              type="range"
              min={0.4}
              max={2.2}
              step={0.05}
              value={bondScale}
              onChange={(e) => setBondScale(parseFloat(e.target.value))}
              className="w-28 accent-[#5eead4] cursor-pointer"
            />
          </div>
          <div className="flex items-center justify-between text-xs pt-1" style={{ borderTop: "1px solid var(--md-sys-color-outline)" }}>
            <span>显示 XYZ 空间坐标轴</span>
            <button
              onClick={() => setShowAxes((a) => !a)}
              className="px-2 py-0.5 rounded-lg text-[11px] cursor-pointer"
              style={{
                background: showAxes ? "var(--md-sys-color-primary-container)" : "transparent",
                color: showAxes ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
              }}
            >
              {showAxes ? "已开启" : "已隐藏"}
            </button>
          </div>
        </div>
      )}

      {/* Compact Never-Clipped Bottom Floating Material 3 Dock */}
      <div className="absolute bottom-3.5 left-1/2 -translate-x-1/2 glass-pill rounded-2xl px-2.5 py-1.5 flex items-center gap-1.5 max-w-[96%]">
        <div
          className="flex items-center p-0.5 rounded-xl shrink-0"
          style={{ background: "rgba(0,0,0,0.22)", border: "1px solid var(--md-sys-color-outline)" }}
        >
          {MODE_OPTIONS.map((opt) => {
            const active = mode === opt.id;
            return (
              <button
                key={opt.id}
                onClick={() => onModeChange(opt.id)}
                className="px-2.5 py-1 rounded-lg text-[11px] font-medium cursor-pointer whitespace-nowrap shrink-0"
                style={{
                  background: active ? "var(--md-sys-color-primary)" : "transparent",
                  color: active ? "var(--md-sys-color-on-primary)" : "var(--md-sys-color-on-surface-muted)",
                }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        <button
          onClick={() => setScaleMenuOpen((v) => !v)}
          className="px-2 py-1 rounded-lg text-[11px] font-medium flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0"
          style={{
            background: scaleMenuOpen ? "var(--md-sys-color-primary-container)" : "transparent",
            color: scaleMenuOpen ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
            border: "1px solid var(--md-sys-color-outline)",
          }}
          title="调整球径、键粗与坐标轴"
        >
          <SlidersHorizontal className="w-3 h-3" />
          <span>尺度</span>
        </button>

        <button
          onClick={() => setShowH((v) => !v)}
          className="px-2 py-1 rounded-lg text-[11px] font-medium flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0"
          style={{
            background: showH ? "var(--md-sys-color-primary-container)" : "transparent",
            color: showH ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
            border: "1px solid var(--md-sys-color-outline)",
          }}
        >
          <Eye className="w-3 h-3" />H
        </button>

        {summary?.cell && (
          <button
            onClick={() => setShowCell((v) => !v)}
            className="px-2 py-1 rounded-lg text-[11px] font-medium flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0"
            style={{
              background: showCell ? "var(--md-sys-color-primary-container)" : "transparent",
              color: showCell ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
              border: "1px solid var(--md-sys-color-outline)",
            }}
          >
            <Box className="w-3 h-3" />
            晶胞
          </button>
        )}
      </div>
    </div>
  );
};
