import React, { useRef } from "react";
import { Download } from "lucide-react";
import type { AnalysisRunResult } from "../../types/studio";

interface Props {
  result: AnalysisRunResult | null;
}

export const AnalysisPlotChart: React.FC<Props> = ({ result }) => {
  const svgRef = useRef<SVGSVGElement | null>(null);

  if (!result) {
    return (
      <div className="studio-surface p-8 text-center space-y-1.5">
        <div className="text-[13px] font-semibold">尚未运行分析项</div>
        <p className="text-[12px]" style={{ color: "var(--text-secondary)" }}>
          请从左侧选择 79 项分析中的任意模块（如 WFN-02 / CORE-01 / OSC 专题）执行实算或解析。
        </p>
      </div>
    );
  }

  const hasPlot = result.plot_x.length > 0 && result.plot_y.length === result.plot_x.length;

  const exportCsv = () => {
    if (!hasPlot) return;
    const rows = [`${result.x_label || "x"},${result.y_label || "y"}`];
    for (let i = 0; i < result.plot_x.length; i++) {
      rows.push(`${result.plot_x[i]},${result.plot_y[i]}`);
    }
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${result.analysis_id}_curve.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const exportSvg = () => {
    if (!svgRef.current) return;
    const xml = new XMLSerializer().serializeToString(svgRef.current);
    const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${result.analysis_id}_plot.svg`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const w = 640;
  const h = 250;
  const padL = 60;
  const padR = 20;
  const padT = 20;
  const padB = 40;

  let pathD = "";
  let pts: Array<{ x: number; y: number; rawX: number; rawY: number }> = [];
  let minX = 0, maxX = 1, minY = 0, maxY = 1;

  if (hasPlot) {
    minX = Math.min(...result.plot_x);
    maxX = Math.max(...result.plot_x);
    minY = Math.min(...result.plot_y);
    maxY = Math.max(...result.plot_y);
    const spanX = Math.max(1e-6, maxX - minX);
    const spanY = Math.max(1e-6, maxY - minY);
    pts = result.plot_x.map((vx, i) => ({
      x: padL + ((vx - minX) / spanX) * (w - padL - padR),
      y: padT + (1 - (result.plot_y[i] - minY) / spanY) * (h - padT - padB),
      rawX: vx,
      rawY: result.plot_y[i],
    }));
    pathD = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  }

  return (
    <div className="studio-surface p-3 space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="mono-num text-[11px] px-1.5 py-0.5 rounded font-semibold" style={{ backgroundColor: "var(--accent-soft)", color: "var(--accent-primary)" }}>
              {result.analysis_id}
            </span>
            <h3 className="text-[13px] font-semibold">{result.title}</h3>
          </div>
          <p className="text-[11.5px] mt-0.5" style={{ color: "var(--text-secondary)" }}>
            状态：{result.status} · 数据来源：MolForge CapabilityResolver
          </p>
        </div>

        {hasPlot && (
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={exportCsv} className="studio-btn !h-7 !px-2.5">
              <Download size={12} />
              <span>CSV</span>
            </button>
            <button type="button" onClick={exportSvg} className="studio-btn !h-7 !px-2.5">
              <Download size={12} />
              <span>SVG</span>
            </button>
          </div>
        )}
      </div>

      {hasPlot ? (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${w} ${h}`}
          className="w-full h-auto rounded-lg"
          style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)" }}
        >
          <line x1={padL} y1={h - padB} x2={w - padR} y2={h - padB} stroke="var(--border-strong)" strokeWidth={1.1} />
          <line x1={padL} y1={padT} x2={padL} y2={h - padB} stroke="var(--border-strong)" strokeWidth={1.1} />

          <path d={pathD} fill="none" stroke="var(--chart-series-1)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
          {pts.length <= 80 &&
            pts.map((p, i) => (
              <circle key={i} cx={p.x} cy={p.y} r={3} fill="var(--chart-series-1)">
                <title>{`(${p.rawX.toFixed(3)}, ${p.rawY.toFixed(3)})`}</title>
              </circle>
            ))}

          <text x={(padL + w - padR) / 2} y={h - 10} textAnchor="middle" fontSize={11} fill="var(--text-secondary)">
            {result.x_label || "Index"}
          </text>
          <text x={16} y={(padT + h - padB) / 2} transform={`rotate(-90 16 ${(padT + h - padB) / 2})`} textAnchor="middle" fontSize={11} fill="var(--text-secondary)">
            {result.y_label || "Value"}
          </text>
          <text x={padL - 6} y={padT + 8} textAnchor="end" fontSize={10} fill="var(--text-muted)" className="mono-num">
            {maxY.toFixed(2)}
          </text>
          <text x={padL - 6} y={h - padB} textAnchor="end" fontSize={10} fill="var(--text-muted)" className="mono-num">
            {minY.toFixed(2)}
          </text>
          <text x={padL} y={h - padB + 14} textAnchor="start" fontSize={10} fill="var(--text-muted)" className="mono-num">
            {minX.toFixed(2)}
          </text>
          <text x={w - padR} y={h - padB + 14} textAnchor="end" fontSize={10} fill="var(--text-muted)" className="mono-num">
            {maxX.toFixed(2)}
          </text>
        </svg>
      ) : (
        <div className="studio-inset p-4 text-[12px]" style={{ color: "var(--text-secondary)" }}>
          该分析返回结构化数值指标（无二维曲线序列）。摘要：<span className="font-medium" style={{ color: "var(--text-primary)" }}>{result.summary}</span>
        </div>
      )}
    </div>
  );
};
