import React from "react";
import type { OrbitCamera, Vec3 } from "../../engine/camera";
import { HARTREE_TO_KCAL_MOL, mapScalarToColor, type SurfaceColormap } from "../../engine/cubeIsosurface";
import type { BinaryMoleculeData } from "../../types/studio";

export interface TorsionOverlayItem {
  type: string;
  side: string;
  atoms: [number, number, number, number];
  angle: number;
  bond_length_a: number;
  interplanar_deg?: number | null;
}

export interface ShortContactOverlayItem {
  kind: string;
  atoms: [number, number];
  distance_a: number;
}

interface ColorBarProps {
  minAu: number;
  maxAu: number;
  palette: SurfaceColormap;
  orientation: "vertical" | "horizontal";
  darkTheme: boolean;
  svgRef?: React.RefObject<SVGSVGElement | null>;
}

function rgbStr(rgb: [number, number, number]): string {
  return `rgb(${Math.round(rgb[0] * 255)},${Math.round(rgb[1] * 255)},${Math.round(rgb[2] * 255)})`;
}

/** Dual-unit vector ColorBar SVG (`a.u.` + `kcal/mol`), explicitly marking white midpoint & neutral 0. */
export const DualUnitColorBarSvg: React.FC<ColorBarProps> = ({
  minAu,
  maxAu,
  palette,
  orientation,
  darkTheme,
  svgRef,
}) => {
  const fg = darkTheme ? "#E2E8F0" : "#1E293B";
  const muted = darkTheme ? "#94A3B8" : "#64748B";
  const span = Math.max(1e-6, maxAu - minAu);
  const midAu = 0.5 * (minAu + maxAu);
  const neutralInRange = minAu <= 0 && maxAu >= 0;
  const neutralFrac = (0 - minAu) / span; // 0=min, 1=max

  const stops = [0, 0.25, 0.5, 0.75, 1].map((t) => {
    const val = minAu + t * span;
    return { t, color: rgbStr(mapScalarToColor(val, minAu, maxAu, palette)) };
  });

  if (orientation === "horizontal") {
    const w = 360;
    const h = 76;
    const bx = 28;
    const bw = 304;
    const by = 28;
    const bh = 16;
    const ticks = [0, 0.25, 0.5, 0.75, 1];
    return (
      <svg
        ref={svgRef}
        xmlns="http://www.w3.org/2000/svg"
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        className="select-none"
      >
        <defs>
          <linearGradient id="molforge-cbar-h" x1="0%" y1="0%" x2="100%" y2="0%">
            {stops.map((s) => (
              <stop key={s.t} offset={`${(s.t * 100).toFixed(1)}%`} stopColor={s.color} />
            ))}
          </linearGradient>
        </defs>
        <text x={bx} y={12} fontSize="10" fontFamily="system-ui, sans-serif" fill={muted}>
          ESP (a.u.)
        </text>
        <text x={bx + bw} y={12} textAnchor="end" fontSize="10" fontFamily="system-ui, sans-serif" fill={muted}>
          {palette} · Mid {(midAu).toFixed(3)} a.u.
        </text>
        <rect x={bx} y={by} width={bw} height={bh} rx={3} fill="url(#molforge-cbar-h)" stroke={fg} strokeWidth={0.8} />
        {ticks.map((t) => {
          const x = bx + t * bw;
          const au = minAu + t * span;
          const kcal = au * HARTREE_TO_KCAL_MOL;
          return (
            <g key={t}>
              <line x1={x} y1={by - 3} x2={x} y2={by} stroke={fg} strokeWidth={1} />
              <text x={x} y={by - 5} textAnchor="middle" fontSize="9.5" fontFamily="monospace" fill={fg}>
                {au.toFixed(3)}
              </text>
              <line x1={x} y1={by + bh} x2={x} y2={by + bh + 3} stroke={fg} strokeWidth={1} />
              <text x={x} y={by + bh + 13} textAnchor="middle" fontSize="9.5" fontFamily="monospace" fill={muted}>
                {kcal.toFixed(1)}
              </text>
            </g>
          );
        })}
        {neutralInRange && Math.abs(neutralFrac - 0.5) > 0.03 && (
          <g>
            <line
              x1={bx + neutralFrac * bw}
              y1={by - 1}
              x2={bx + neutralFrac * bw}
              y2={by + bh + 1}
              stroke="#10B981"
              strokeWidth={1.6}
              strokeDasharray="2,1"
            />
            <text
              x={bx + neutralFrac * bw}
              y={by + bh + 25}
              textAnchor="middle"
              fontSize="9"
              fontFamily="monospace"
              fill="#10B981"
            >
              0.000
            </text>
          </g>
        )}
        <text x={bx} y={h - 3} fontSize="9.5" fontFamily="system-ui, sans-serif" fill={muted}>
          kcal/mol
        </text>
      </svg>
    );
  }

  // Vertical ColorBar: top = maxAu, bottom = minAu
  const w = 156;
  const h = 240;
  const bx = 64;
  const bw = 18;
  const by = 24;
  const bh = 192;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <svg
      ref={svgRef}
      xmlns="http://www.w3.org/2000/svg"
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      className="select-none"
    >
      <defs>
        <linearGradient id="molforge-cbar-v" x1="0%" y1="100%" x2="0%" y2="0%">
          {stops.map((s) => (
            <stop key={s.t} offset={`${(s.t * 100).toFixed(1)}%`} stopColor={s.color} />
          ))}
        </linearGradient>
      </defs>
      <text x={bx - 4} y={13} textAnchor="end" fontSize="9.5" fontFamily="system-ui, sans-serif" fill={fg}>
        a.u.
      </text>
      <text x={bx + bw + 4} y={13} textAnchor="start" fontSize="9.5" fontFamily="system-ui, sans-serif" fill={muted}>
        kcal/mol
      </text>
      <rect x={bx} y={by} width={bw} height={bh} rx={3} fill="url(#molforge-cbar-v)" stroke={fg} strokeWidth={0.8} />
      {ticks.map((t) => {
        const y = by + (1 - t) * bh;
        const au = minAu + t * span;
        const kcal = au * HARTREE_TO_KCAL_MOL;
        return (
          <g key={t}>
            <line x1={bx - 4} y1={y} x2={bx} y2={y} stroke={fg} strokeWidth={1} />
            <text x={bx - 6} y={y + 3} textAnchor="end" fontSize="9.5" fontFamily="monospace" fill={fg}>
              {au.toFixed(3)}
            </text>
            <line x1={bx + bw} y1={y} x2={bx + bw + 4} y2={y} stroke={fg} strokeWidth={1} />
            <text x={bx + bw + 6} y={y + 3} textAnchor="start" fontSize="9.5" fontFamily="monospace" fill={muted}>
              {kcal.toFixed(1)}
            </text>
          </g>
        );
      })}
      {neutralInRange && Math.abs(neutralFrac - 0.5) > 0.03 && (
        <line
          x1={bx - 2}
          y1={by + (1 - neutralFrac) * bh}
          x2={bx + bw + 2}
          y2={by + (1 - neutralFrac) * bh}
          stroke="#10B981"
          strokeWidth={1.6}
          strokeDasharray="3,2"
        />
      )}
      <text x={w / 2} y={h - 5} textAnchor="middle" fontSize="9" fontFamily="system-ui, sans-serif" fill={muted}>
        {palette} · 白点 {midAu.toFixed(3)} a.u.
      </text>
    </svg>
  );
};

interface AnnotationProps {
  width: number;
  height: number;
  camera: OrbitCamera;
  data: BinaryMoleculeData | null;
  torsions: TorsionOverlayItem[];
  shortContacts: ShortContactOverlayItem[];
  darkTheme: boolean;
  svgRef?: React.RefObject<SVGSVGElement | null>;
}

/** 3D -> 2D projected crisp vector annotations (`θ`, bond lengths, short contacts). */
export const AnnotationOverlaySvg: React.FC<AnnotationProps> = ({
  width,
  height,
  camera,
  data,
  torsions,
  shortContacts,
  darkTheme,
  svgRef,
}) => {
  if (!data || width < 10 || height < 10 || (torsions.length === 0 && shortContacts.length === 0)) {
    return null;
  }
  const atomPos = (oneBased: number): Vec3 | null => {
    const i = oneBased - 1;
    if (i < 0 || i >= data.numAtoms) return null;
    return [data.coords[i * 3], data.coords[i * 3 + 1], data.coords[i * 3 + 2]];
  };

  const labelBg = darkTheme ? "rgba(15, 23, 42, 0.86)" : "rgba(255, 255, 255, 0.90)";
  const labelFg = darkTheme ? "#F8FAFC" : "#0F172A";

  return (
    <svg
      ref={svgRef}
      xmlns="http://www.w3.org/2000/svg"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="pointer-events-none absolute inset-0 z-10"
    >
      {torsions.slice(0, 6).map((t, idx) => {
        const p2 = atomPos(t.atoms[1]);
        const p3 = atomPos(t.atoms[2]);
        if (!p2 || !p3) return null;
        const mid: Vec3 = [0.5 * (p2[0] + p3[0]), 0.5 * (p2[1] + p3[1]), 0.5 * (p2[2] + p3[2])];
        const s1 = camera.projectWorldToScreen(p2, width, height);
        const s2 = camera.projectWorldToScreen(p3, width, height);
        const sm = camera.projectWorldToScreen(mid, width, height);
        if (!sm.visible) return null;
        const dy = idx % 2 === 0 ? -24 : 26;
        const text = `θ${idx + 1}=${Math.abs(t.angle).toFixed(1)}° · d=${t.bond_length_a.toFixed(3)}Å`;
        const boxW = text.length * 6.4 + 12;
        return (
          <g key={`tor-${idx}`}>
            <line
              x1={s1.x}
              y1={s1.y}
              x2={s2.x}
              y2={s2.y}
              stroke="#14B8A6"
              strokeWidth={2.5}
              strokeDasharray="4,2"
            />
            <line x1={sm.x} y1={sm.y} x2={sm.x} y2={sm.y + dy} stroke="#14B8A6" strokeWidth={1.2} />
            <rect
              x={sm.x - boxW / 2}
              y={sm.y + dy - 10}
              width={boxW}
              height={18}
              rx={4}
              fill={labelBg}
              stroke="#14B8A6"
              strokeWidth={1}
            />
            <text
              x={sm.x}
              y={sm.y + dy + 2.5}
              textAnchor="middle"
              fontSize="10.5"
              fontWeight="600"
              fontFamily="monospace"
              fill={labelFg}
            >
              {text}
            </text>
          </g>
        );
      })}

      {shortContacts.slice(0, 4).map((sc, idx) => {
        const pa = atomPos(sc.atoms[0]);
        const pb = atomPos(sc.atoms[1]);
        if (!pa || !pb) return null;
        const sa = camera.projectWorldToScreen(pa, width, height);
        const sb = camera.projectWorldToScreen(pb, width, height);
        const mx = 0.5 * (sa.x + sb.x);
        const my = 0.5 * (sa.y + sb.y);
        return (
          <g key={`sc-${idx}`}>
            <line
              x1={sa.x}
              y1={sa.y}
              x2={sb.x}
              y2={sb.y}
              stroke="#F59E0B"
              strokeWidth={1.8}
              strokeDasharray="3,3"
            />
            <text
              x={mx}
              y={my - 5}
              textAnchor="middle"
              fontSize="10"
              fontWeight="600"
              fontFamily="monospace"
              fill="#F59E0B"
            >
              {sc.kind} {sc.distance_a.toFixed(2)}Å
            </text>
          </g>
        );
      })}
    </svg>
  );
};

async function svgElementToImage(svgEl: SVGSVGElement): Promise<HTMLImageElement> {
  const xml = new XMLSerializer().serializeToString(svgEl);
  const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  return await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = (e) => {
      URL.revokeObjectURL(url);
      reject(e);
    };
    img.src = url;
  });
}

/** Composite high-res WebGPU canvas + projected SVG annotations + dual-unit vector ColorBar into one PNG data URL. */
export async function composeHighResPublicationPng(
  hdCanvas: HTMLCanvasElement,
  overlaySvg: SVGSVGElement | null,
  colorBarSvg: SVGSVGElement | null,
  darkTheme: boolean,
  transparentBg: boolean
): Promise<string> {
  const w = hdCanvas.width;
  const h = hdCanvas.height;
  const out = document.createElement("canvas");
  out.width = w;
  out.height = h;
  const ctx = out.getContext("2d");
  if (!ctx) return hdCanvas.toDataURL("image/png");

  if (!transparentBg) {
    ctx.fillStyle = darkTheme ? "#0B1220" : "#FFFFFF";
    ctx.fillRect(0, 0, w, h);
  }
  ctx.drawImage(hdCanvas, 0, 0, w, h);

  if (overlaySvg) {
    const img = await svgElementToImage(overlaySvg);
    ctx.drawImage(img, 0, 0, w, h);
  }

  if (colorBarSvg) {
    const img = await svgElementToImage(colorBarSvg);
    const scale = Math.max(1, w / 1000);
    const cw = Math.round((colorBarSvg.viewBox.baseVal.width || colorBarSvg.clientWidth || 160) * scale);
    const ch = Math.round((colorBarSvg.viewBox.baseVal.height || colorBarSvg.clientHeight || 220) * scale);
    const pad = Math.round(24 * scale);
    ctx.drawImage(img, w - cw - pad, h - ch - pad, cw, ch);
  }

  return out.toDataURL("image/png");
}
