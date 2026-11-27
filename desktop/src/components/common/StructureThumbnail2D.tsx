import React, { useMemo } from "react";
import type { Preview2DStructure } from "../../types/studio";
import { useStudioStore } from "../../store/useStudioStore";

interface Props {
  preview?: Preview2DStructure | null;
  width?: number;
  height?: number;
  className?: string;
}

export const StructureThumbnail2D: React.FC<Props> = ({
  preview,
  width = 160,
  height = 100,
  className = "",
}) => {
  const theme = useStudioStore((s) => s.theme);
  const bondStroke = theme === "arctic" ? "#33475B" : "#94A7BD";
  const labelBg = theme === "arctic" ? "#FFFFFF" : "#172336";

  const layout = useMemo(() => {
    if (!preview || preview.atoms.length === 0) return null;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const a of preview.atoms) {
      if (a.x2 < minX) minX = a.x2;
      if (a.y2 < minY) minY = a.y2;
      if (a.x2 > maxX) maxX = a.x2;
      if (a.y2 > maxY) maxY = a.y2;
    }
    const spanX = Math.max(1.2, maxX - minX);
    const spanY = Math.max(1.2, maxY - minY);
    const pad = 16;
    const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY);
    const cx = 0.5 * (minX + maxX);
    const cy = 0.5 * (minY + maxY);
    const pt = (x: number, y: number): [number, number] => [
      width * 0.5 + (x - cx) * scale,
      height * 0.5 - (y - cy) * scale,
    ];
    return { pts: preview.atoms.map((a) => pt(a.x2, a.y2)) };
  }, [preview, width, height]);

  if (!preview || !layout || preview.atoms.length === 0) {
    return (
      <div
        className={`flex items-center justify-center text-[11px] ${className}`}
        style={{ width, height, color: "var(--text-muted)" }}
      >
        无二维结构
      </div>
    );
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-label="分子二维结构缩略图"
    >
      {preview.bonds.map((b, idx) => {
        const p1 = layout.pts[b.i];
        const p2 = layout.pts[b.j];
        if (!p1 || !p2) return null;
        const dx = p2[0] - p1[0];
        const dy = p2[1] - p1[1];
        const len = Math.hypot(dx, dy) || 1;
        const nx = (-dy / len) * 2.6;
        const ny = (dx / len) * 2.6;
        if (b.order === 2) {
          return (
            <g key={idx}>
              <line x1={p1[0] + nx * 0.55} y1={p1[1] + ny * 0.55} x2={p2[0] + nx * 0.55} y2={p2[1] + ny * 0.55} stroke={bondStroke} strokeWidth={1.35} strokeLinecap="round" />
              <line x1={p1[0] - nx * 0.55} y1={p1[1] - ny * 0.55} x2={p2[0] - nx * 0.55} y2={p2[1] - ny * 0.55} stroke={bondStroke} strokeWidth={1.35} strokeLinecap="round" />
            </g>
          );
        }
        if (b.order === 3) {
          return (
            <g key={idx}>
              <line x1={p1[0]} y1={p1[1]} x2={p2[0]} y2={p2[1]} stroke={bondStroke} strokeWidth={1.25} />
              <line x1={p1[0] + nx} y1={p1[1] + ny} x2={p2[0] + nx} y2={p2[1] + ny} stroke={bondStroke} strokeWidth={1.1} />
              <line x1={p1[0] - nx} y1={p1[1] - ny} x2={p2[0] - nx} y2={p2[1] - ny} stroke={bondStroke} strokeWidth={1.1} />
            </g>
          );
        }
        return (
          <line
            key={idx}
            x1={p1[0]}
            y1={p1[1]}
            x2={p2[0]}
            y2={p2[1]}
            stroke={bondStroke}
            strokeWidth={1.45}
            strokeDasharray={b.aromatic ? "3 2" : undefined}
            strokeLinecap="round"
          />
        );
      })}
      {preview.atoms.map((a, idx) => {
        if (a.symbol === "C" || a.symbol === "H") return null;
        const p = layout.pts[idx];
        const col = `rgb(${a.color[0]},${a.color[1]},${a.color[2]})`;
        return (
          <g key={idx}>
            <circle cx={p[0]} cy={p[1]} r={6} fill={labelBg} />
            <text
              x={p[0]}
              y={p[1] + 3.5}
              textAnchor="middle"
              fontSize={9.5}
              fontWeight={700}
              fill={col}
              fontFamily="Arial, sans-serif"
            >
              {a.symbol}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
