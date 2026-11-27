import React, { useRef, useState } from "react";
import { Download } from "lucide-react";
import type { QcParsedOrbitalResult, TightBindingResult } from "../../types/studio";

interface Props {
  tbResult: TightBindingResult | null;
  qcParsed: QcParsedOrbitalResult | null;
  activeName: string;
}

export const EnergyLadderChart: React.FC<Props> = ({ tbResult, qcParsed, activeName }) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hoveredCol, setHoveredCol] = useState<string | null>(null);

  const exportSvg = () => {
    if (!svgRef.current) return;
    const xml = new XMLSerializer().serializeToString(svgRef.current);
    const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${activeName.replace(/\s+/g, "_")}_energy_ladder.svg`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const columns: Array<{
    name: string;
    homo: number;
    lumo: number;
    color: string;
    marker: "circle" | "square" | "triangle" | "diamond";
    source: string;
  }> = [];

  if (tbResult && typeof tbResult.homo_ev === "number" && typeof tbResult.lumo_ev === "number") {
    columns.push({
      name: tbResult.molecule_name || activeName,
      homo: tbResult.homo_ev,
      lumo: tbResult.lumo_ev,
      color: "var(--chart-series-1)",
      marker: "circle",
      source: tbResult.method || "Tight-Binding 实时实算",
    });
  }
  if (qcParsed) {
    columns.push({
      name: `${qcParsed.kind.toUpperCase()} 导入结果`,
      homo: qcParsed.homo_ev,
      lumo: qcParsed.lumo_ev,
      color: "var(--chart-series-4)",
      marker: "diamond",
      source: qcParsed.method,
    });
  }

  const refs = tbResult?.references ?? [
    { name: "PM6 (经典给体)", homo_ev: -5.5, lumo_ev: -3.61, color: "var(--chart-series-2)" },
    { name: "Y6 (经典受体)", homo_ev: -5.65, lumo_ev: -4.1, color: "var(--chart-series-3)" },
  ];
  refs.slice(0, 3).forEach((r, idx) => {
    columns.push({
      name: r.name.split(" ")[0],
      homo: r.homo_ev,
      lumo: r.lumo_ev,
      color: idx === 0 ? "var(--chart-series-2)" : idx === 1 ? "var(--chart-series-3)" : "var(--chart-series-4)",
      marker: idx === 0 ? "square" : "triangle",
      source: "OSC 基准材料库",
    });
  });

  const w = 680;
  const h = 300;
  const padL = 64;
  const padR = 24;
  const padT = 26;
  const padB = 42;

  const allE = columns.flatMap((c) => [c.homo, c.lumo]);
  const eMin = Math.floor(Math.min(-7.2, ...allE) * 2) / 2 - 0.3;
  const eMax = Math.ceil(Math.max(-1.8, ...allE) * 2) / 2 + 0.3;
  const yOf = (ev: number) => padT + ((eMax - ev) / Math.max(1e-4, eMax - eMin)) * (h - padT - padB);
  const ticks: number[] = [];
  for (let v = Math.ceil(eMin); v <= Math.floor(eMax); v += 1) ticks.push(v);

  return (
    <div className="studio-surface p-3 space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-semibold">前线分子轨道能级阶梯图 (HOMO / LUMO Energy Ladder)</h3>
          <p className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
            纵轴单位：真空能级相对能量 (eV) · 实线=当前实算 · 虚线/菱方符号=参照文献体系
          </p>
        </div>
        <button type="button" onClick={exportSvg} className="studio-btn !h-7 !px-2.5">
          <Download size={12.5} />
          <span>导出 SVG</span>
        </button>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-auto rounded-lg"
        style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)" }}
      >
        {/* Y Axis Title & Ticks */}
        <text x={16} y={h / 2} transform={`rotate(-90 16 ${h / 2})`} textAnchor="middle" fontSize={11} fill="var(--text-secondary)">
          Orbital Energy (eV)
        </text>
        {ticks.map((ev) => {
          const y = yOf(ev);
          return (
            <g key={ev}>
              <line x1={padL} y1={y} x2={w - padR} y2={y} stroke="var(--border-subtle)" strokeDasharray="3 3" strokeWidth={0.9} />
              <text x={padL - 8} y={y + 3.5} textAnchor="end" fontSize={10.5} fill="var(--text-muted)" fontFamily="Consolas, monospace">
                {ev.toFixed(1)}
              </text>
            </g>
          );
        })}

        {/* Columns */}
        {columns.map((c, idx) => {
          const colW = (w - padL - padR) / Math.max(1, columns.length);
          const cx = padL + colW * (idx + 0.5);
          const barHalf = Math.min(44, colW * 0.28);
          const yH = yOf(c.homo);
          const yL = yOf(c.lumo);
          const gap = (c.lumo - c.homo).toFixed(2);
          const isHov = hoveredCol === c.name;

          return (
            <g
              key={c.name}
              onMouseEnter={() => setHoveredCol(c.name)}
              onMouseLeave={() => setHoveredCol(null)}
              style={{ opacity: hoveredCol && !isHov ? 0.5 : 1 }}
            >
              <line x1={cx} y1={yL} x2={cx} y2={yH} stroke={c.color} strokeDasharray="3 2.5" strokeWidth={1.3} />
              {/* LUMO bar */}
              <line x1={cx - barHalf} y1={yL} x2={cx + barHalf} y2={yL} stroke={c.color} strokeWidth={3.2} strokeLinecap="round" />
              {/* HOMO bar */}
              <line x1={cx - barHalf} y1={yH} x2={cx + barHalf} y2={yH} stroke={c.color} strokeWidth={3.2} strokeLinecap="round" />
              {/* Shape Marker for colorblind differentiation */}
              {c.marker === "circle" && <circle cx={cx} cy={yL} r={3.8} fill={c.color} />}
              {c.marker === "square" && <rect x={cx - 3.5} y={yL - 3.5} width={7} height={7} fill={c.color} />}
              {c.marker === "triangle" && <polygon points={`${cx},${yL - 4.5} ${cx - 4},${yL + 3.5} ${cx + 4},${yL + 3.5}`} fill={c.color} />}
              {c.marker === "diamond" && <polygon points={`${cx},${yL - 4.5} ${cx + 4.5},${yL} ${cx},${yL + 4.5} ${cx - 4.5},${yL}`} fill={c.color} />}

              <text x={cx} y={yL - 8} textAnchor="middle" fontSize={10.5} fontWeight={600} fill={c.color} fontFamily="Consolas, monospace">
                L {c.lumo.toFixed(2)}
              </text>
              <text x={cx} y={yH + 13} textAnchor="middle" fontSize={10.5} fontWeight={600} fill={c.color} fontFamily="Consolas, monospace">
                H {c.homo.toFixed(2)}
              </text>
              <text x={cx} y={(yH + yL) * 0.5 + 3} textAnchor="middle" fontSize={10} fill="var(--text-primary)" fontFamily="Consolas, monospace">
                Eg={gap} eV
              </text>
              <text x={cx} y={h - 14} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--text-primary)">
                {c.name}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
