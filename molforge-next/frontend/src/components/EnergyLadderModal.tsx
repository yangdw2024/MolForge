import React, { useEffect, useState } from "react";
import { Check, Copy, Cpu, FileCode2, X, Zap } from "lucide-react";
import { molApi } from "../services/api";
import type { DocumentSummary, TightBindingResult } from "../types/molforge";

interface Props {
  open: boolean;
  onClose: () => void;
  summary: DocumentSummary | null;
}

export const EnergyLadderModal: React.FC<Props> = ({ open, onClose, summary }) => {
  const [tb, setTb] = useState<TightBindingResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<"ladder" | "gjf" | "rest">("ladder");
  const [inputCode, setInputCode] = useState("");
  const [copied, setCopied] = useState(false);

  const runCompute = async () => {
    setLoading(true);
    try {
      const res = await molApi.computeTB();
      setTb(res);
    } finally {
      setLoading(false);
    }
  };

  const loadQcTemplate = async (kind: "gaussian" | "rest") => {
    setTab(kind === "gaussian" ? "gjf" : "rest");
    const res = await molApi.exportQcInput(kind);
    setInputCode(res.content);
  };

  useEffect(() => {
    if (open) {
      void runCompute();
    }
  }, [open, summary?.revision]);

  if (!open) return null;

  const items: Array<{ name: string; homo: number; lumo: number; color: string }> = [];
  const refs = tb?.references || [];
  if (refs[0]) items.push({ name: refs[0].name.split(" ")[0], homo: refs[0].homo_ev, lumo: refs[0].lumo_ev, color: "#60A5FA" });
  if (tb && !tb.skipped && !tb.error && typeof tb.homo_ev === "number" && typeof tb.lumo_ev === "number") {
    items.push({
      name: summary?.name || "当前分子",
      homo: tb.homo_ev,
      lumo: tb.lumo_ev,
      color: "#5EEAD4",
    });
  }
  if (refs[1]) items.push({ name: refs[1].name.split(" ")[0], homo: refs[1].homo_ev, lumo: refs[1].lumo_ev, color: "#FB923C" });

  const allE = items.flatMap((x) => [x.homo, x.lumo]);
  const eMin = allE.length ? Math.min(-6.8, Math.min(...allE) - 0.6) : -6.8;
  const eMax = allE.length ? Math.max(-1.6, Math.max(...allE) + 0.6) : -1.6;
  const toY = (ev: number) => 36 + ((eMax - ev) / Math.max(0.5, eMax - eMin)) * 228;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6" style={{ background: "rgba(3, 7, 12, 0.72)", backdropFilter: "blur(8px)" }}>
      <div
        className="w-full max-w-4xl rounded-3xl overflow-hidden flex flex-col max-h-[88vh]"
        style={{
          background: "var(--md-sys-color-surface)",
          border: "1px solid var(--md-sys-color-outline-strong)",
          boxShadow: "var(--md-sys-shadow-floating)",
        }}
      >
        {/* Header */}
        <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-2xl flex items-center justify-center" style={{ background: "var(--md-sys-color-primary-container)", color: "var(--md-sys-color-primary)" }}>
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold">MolForge 量化电子结构与 OSC 能级工作台</h2>
              <p className="text-xs" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                实时紧束缚 HOMO-LUMO 求解 · 给体/受体能级阶梯对比 · Gaussian / 复旦 REST 输入卡
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl hover:bg-white/5 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation tabs */}
        <div className="px-6 pt-3 flex items-center gap-2" style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}>
          <button
            onClick={() => setTab("ladder")}
            className="px-3.5 py-2 text-xs font-medium rounded-t-xl cursor-pointer flex items-center gap-1.5"
            style={{
              borderBottom: tab === "ladder" ? "2px solid var(--md-sys-color-primary)" : "2px solid transparent",
              color: tab === "ladder" ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
            }}
          >
            <Cpu className="w-3.5 h-3.5" />
            实时轨道能级与 OSC 对比图
          </button>
          <button
            onClick={() => void loadQcTemplate("gaussian")}
            className="px-3.5 py-2 text-xs font-medium rounded-t-xl cursor-pointer flex items-center gap-1.5"
            style={{
              borderBottom: tab === "gjf" ? "2px solid var(--md-sys-color-primary)" : "2px solid transparent",
              color: tab === "gjf" ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
            }}
          >
            <FileCode2 className="w-3.5 h-3.5" />
            Gaussian 16 (.gjf)
          </button>
          <button
            onClick={() => void loadQcTemplate("rest")}
            className="px-3.5 py-2 text-xs font-medium rounded-t-xl cursor-pointer flex items-center gap-1.5"
            style={{
              borderBottom: tab === "rest" ? "2px solid var(--md-sys-color-primary)" : "2px solid transparent",
              color: tab === "rest" ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
            }}
          >
            <FileCode2 className="w-3.5 h-3.5" />
            复旦 REST (ctrl.in)
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          {tab === "ladder" ? (
            <div className="space-y-4">
              {tb?.skipped ? (
                <div className="rounded-2xl p-4 text-xs" style={{ background: "rgba(251,146,60,0.12)", color: "#fb923c" }}>
                  {tb.reason}
                </div>
              ) : (
                <div className="grid grid-cols-4 gap-3">
                  <div className="rounded-2xl p-3" style={{ background: "var(--md-sys-color-surface-low)" }}>
                    <div className="text-[11px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>求解引擎</div>
                    <div className="text-xs font-semibold mt-1">{tb?.method || (loading ? "计算中..." : "Tight-Binding MO")}</div>
                  </div>
                  <div className="rounded-2xl p-3" style={{ background: "var(--md-sys-color-surface-low)" }}>
                    <div className="text-[11px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>HOMO</div>
                    <div className="text-base font-bold mono-num mt-0.5" style={{ color: "var(--md-sys-color-secondary)" }}>
                      {typeof tb?.homo_ev === "number" ? `${tb.homo_ev.toFixed(3)} eV` : "—"}
                    </div>
                  </div>
                  <div className="rounded-2xl p-3" style={{ background: "var(--md-sys-color-surface-low)" }}>
                    <div className="text-[11px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>LUMO</div>
                    <div className="text-base font-bold mono-num mt-0.5" style={{ color: "var(--md-sys-color-tertiary)" }}>
                      {typeof tb?.lumo_ev === "number" ? `${tb.lumo_ev.toFixed(3)} eV` : "—"}
                    </div>
                  </div>
                  <div className="rounded-2xl p-3" style={{ background: "var(--md-sys-color-surface-low)" }}>
                    <div className="text-[11px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>光学 / 带隙 Eg</div>
                    <div className="text-base font-bold mono-num mt-0.5" style={{ color: "var(--md-sys-color-primary)" }}>
                      {typeof tb?.gap_ev === "number" ? `${tb.gap_ev.toFixed(3)} eV` : "—"}
                    </div>
                  </div>
                </div>
              )}

              {/* SVG Interactive Energy Ladder */}
              <div className="rounded-2xl p-4" style={{ background: "#091018", border: "1px solid var(--md-sys-color-outline)" }}>
                <svg viewBox="0 0 760 310" className="w-full h-72">
                  {[-2, -3, -4, -5, -6].map((ev) => {
                    if (ev < eMin || ev > eMax) return null;
                    const y = toY(ev);
                    return (
                      <g key={ev}>
                        <line x1={68} y1={y} x2={730} y2={y} stroke="#1d2f44" strokeDasharray="4 4" />
                        <text x={58} y={y} fill="#8ea3b8" fontSize={11} textAnchor="end" dominantBaseline="central" className="mono-num">
                          {ev.toFixed(1)} eV
                        </text>
                      </g>
                    );
                  })}
                  <line x1={68} y1={24} x2={68} y2={274} stroke="#364a61" />

                  {items.map((it, idx) => {
                    const colW = 650 / Math.max(1, items.length);
                    const cx = 74 + (idx + 0.5) * colW;
                    const yH = toY(it.homo);
                    const yL = toY(it.lumo);
                    const gap = Math.abs(it.lumo - it.homo);
                    return (
                      <g key={it.name}>
                        <rect x={cx - 46} y={yL} width={92} height={Math.max(4, yH - yL)} fill={it.color} opacity={0.14} rx={8} />
                        <line x1={cx - 52} y1={yL} x2={cx + 52} y2={yL} stroke={it.color} strokeWidth={3.5} strokeLinecap="round" />
                        <line x1={cx - 52} y1={yH} x2={cx + 52} y2={yH} stroke={it.color} strokeWidth={3.5} strokeLinecap="round" />
                        <line x1={cx} y1={yL + 4} x2={cx} y2={yH - 4} stroke={it.color} strokeDasharray="3 3" opacity={0.75} />
                        <text x={cx} y={yL - 10} fill="#e6eef6" fontSize={11} fontWeight={600} textAnchor="middle" className="mono-num">
                          LUMO {it.lumo.toFixed(2)}
                        </text>
                        <text x={cx} y={(yL + yH) * 0.5} fill={it.color} fontSize={11} fontWeight={700} textAnchor="middle" dominantBaseline="central" className="mono-num">
                          Eg={gap.toFixed(2)} eV
                        </text>
                        <text x={cx} y={yH + 16} fill="#cbd5e1" fontSize={11} fontWeight={600} textAnchor="middle" className="mono-num">
                          HOMO {it.homo.toFixed(2)}
                        </text>
                        <text x={cx} y={294} fill="#e6eef6" fontSize={12} fontWeight={600} textAnchor="middle">
                          {it.name}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                  基于当前活动分子实时生成，可直接提交计算集群
                </span>
                <button
                  onClick={() => {
                    void navigator.clipboard.writeText(inputCode);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1800);
                  }}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 cursor-pointer"
                  style={{ background: "var(--md-sys-color-primary)", color: "var(--md-sys-color-on-primary)" }}
                >
                  {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? "已复制" : "复制输入卡"}
                </button>
              </div>
              <pre
                className="rounded-2xl p-4 text-xs mono-num overflow-x-auto max-h-96 leading-relaxed"
                style={{ background: "#091018", border: "1px solid var(--md-sys-color-outline)", color: "#cbd5e1" }}
              >
                {inputCode}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
