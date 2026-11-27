import React, { useEffect, useState } from "react";
import { BarChart3, RefreshCw, Zap } from "lucide-react";
import { useStudioStore } from "../../store/useStudioStore";
import { molApi } from "../../services/api";
import type { TightBindingResult } from "../../types/studio";
import { FloatingWindow } from "./FloatingWindow";

interface OrbitalLadderModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialData?: TightBindingResult | null;
}

export const OrbitalLadderModal: React.FC<OrbitalLadderModalProps> = ({
  isOpen,
  onClose,
  initialData,
}) => {
  const summary = useStudioStore((s) => s.summary);
  const [data, setData] = useState<TightBindingResult | null>(initialData ?? null);
  const [loading, setLoading] = useState(false);

  const fetchTightBinding = async () => {
    setLoading(true);
    try {
      const res = await molApi.computeTB();
      setData(res);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && !data) {
      void fetchTightBinding();
    }
  }, [isOpen]);

  // 未求解时不显示任何伪造默认值
  const homo = data?.homo_ev ?? null;
  const lumo = data?.lumo_ev ?? null;
  const gap = data?.gap_ev ?? (homo !== null && lumo !== null ? Math.abs(lumo - homo) : null);
  const s1 = data?.transitions?.[0];

  // 能级阶梯动态刻度：所有能级条按真实 eV 值在同一坐标轴上定位
  const bench = { pm6: { homo: -5.5, lumo: -3.61 }, y6: { homo: -5.65, lumo: -4.1 } };
  const scale = (() => {
    const vals = [bench.pm6.homo, bench.pm6.lumo, bench.y6.homo, bench.y6.lumo];
    if (homo !== null) vals.push(homo);
    if (lumo !== null) vals.push(lumo);
    const lo = Math.min(...vals) - 0.6;
    const hi = Math.max(...vals) + 0.6;
    const H = 140; // px 可用高度
    return { lo, hi, y: (e: number) => ((hi - e) / (hi - lo)) * H, H };
  })();
  const ticks = [0, 1, 2, 3].map((i) => scale.hi - ((scale.hi - scale.lo) * i) / 3);

  return (
    <FloatingWindow
      id="orbital-ladder-layer"
      title={`前线分子轨道与能级阶梯 · ${summary?.name ?? "分子"} · 扩展休克尔紧束缚`}
      icon={<BarChart3 size={14} style={{ color: "var(--accent-primary)" }} />}
      isOpen={isOpen}
      onClose={onClose}
      initialPos={{ x: 200, y: 110 }}
      initialSize={{ width: 480, height: 480 }}
      headerExtra={
        <button
          type="button"
          onClick={() => void fetchTightBinding()}
          disabled={loading}
          className="h-6 px-2 rounded text-[11px] font-medium flex items-center gap-1 cursor-pointer transition-colors"
          style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}
          title="重新求解紧束缚"
        >
          <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          <span>求解</span>
        </button>
      }
    >
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-[12px]">
        {/* Core Metrics Cards */}
        <div className="grid grid-cols-3 gap-2">
          <div
            className="p-2.5 rounded-xl border flex flex-col"
            style={{ backgroundColor: "var(--bg-panel)", borderColor: "var(--border-subtle)" }}
          >
            <span className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>HOMO (最高占据)</span>
            <span className="mono-num text-[16px] font-bold text-[#60A5FA] mt-0.5">
              {homo !== null ? `${homo.toFixed(3)} eV` : "—"}
            </span>
          </div>

          <div
            className="p-2.5 rounded-xl border flex flex-col"
            style={{ backgroundColor: "var(--bg-panel)", borderColor: "var(--border-subtle)" }}
          >
            <span className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>LUMO (最低未占)</span>
            <span className="mono-num text-[16px] font-bold text-[#F87171] mt-0.5">
              {lumo !== null ? `${lumo.toFixed(3)} eV` : "—"}
            </span>
          </div>

          <div
            className="p-2.5 rounded-xl border flex flex-col"
            style={{ backgroundColor: "var(--bg-panel)", borderColor: "var(--border-subtle)" }}
          >
            <span className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>基础能隙 Eg</span>
            <span className="mono-num text-[16px] font-bold text-[var(--accent-primary)] mt-0.5">
              {gap !== null ? `${gap.toFixed(3)} eV` : "—"}
            </span>
          </div>
        </div>

        {/* Energy Ladder Visualization */}
        <div
          className="p-3 rounded-xl border"
          style={{ backgroundColor: "var(--bg-primary)", borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold" style={{ color: "var(--text-secondary)" }}>
              能级阶梯图 (EHT 当前分子 vs 文献参考 PM6 / Y6)
            </span>
            <span className="mono-num text-[10.5px]" style={{ color: "var(--text-muted)" }}>
              单位: eV
            </span>
          </div>

          <div className="relative w-full border-b pb-2" style={{ borderColor: "var(--border-subtle)", height: scale.H + 34 }}>
            {/* Energy Axis — 动态刻度 */}
            <div className="absolute left-0 top-0 w-9 text-[9px] mono-num opacity-50" style={{ height: scale.H }}>
              {ticks.map((t, i) => (
                <span key={i} className="absolute left-0" style={{ top: scale.y(t) - 5 }}>
                  {t.toFixed(1)}
                </span>
              ))}
            </div>

            {/* Molecule Ladder Column — 按真实 eV 定位 */}
            <div className="absolute left-12 top-0 w-28" style={{ height: scale.H }}>
              <span className="absolute -top-0.5 left-0 w-full text-center text-[10.5px] font-semibold text-[var(--accent-primary)]">
                当前分子
              </span>
              {homo !== null && lumo !== null ? (
                <>
                  <div
                    className="absolute w-20 left-4 h-1 rounded bg-[#F87171]"
                    style={{ top: scale.y(lumo) }}
                    title={`LUMO: ${lumo.toFixed(3)} eV`}
                  />
                  <div
                    className="absolute left-14 w-1 border-l-2 border-dashed flex items-center justify-center text-[9.5px] mono-num"
                    style={{
                      top: scale.y(lumo) + 4,
                      height: Math.max(10, scale.y(homo) - scale.y(lumo) - 8),
                      borderColor: "var(--accent-primary)",
                      color: "var(--accent-primary)",
                    }}
                  >
                    {gap !== null ? `${gap.toFixed(2)}eV` : ""}
                  </div>
                  <div
                    className="absolute w-20 left-4 h-1 rounded bg-[#60A5FA]"
                    style={{ top: scale.y(homo) }}
                    title={`HOMO: ${homo.toFixed(3)} eV`}
                  />
                </>
              ) : (
                <span className="absolute left-0 w-full text-center text-[10px]" style={{ top: scale.H / 2, color: "var(--text-muted)" }}>
                  未求解 · 点右上「求解」
                </span>
              )}
            </div>

            {/* PM6 Donor Benchmark — 文献参考值，同刻度定位 */}
            <div className="absolute left-44 top-0 w-24 opacity-75" style={{ height: scale.H }}>
              <span className="absolute -top-0.5 left-0 w-full text-center text-[10px] font-medium" style={{ color: "var(--text-muted)" }}>
                给体 PM6
              </span>
              <div className="absolute w-16 left-4 h-1 rounded bg-[#F87171]/60" style={{ top: scale.y(bench.pm6.lumo) }} />
              <div
                className="absolute left-12 w-1 border-l border-dashed"
                style={{ top: scale.y(bench.pm6.lumo) + 4, height: Math.max(6, scale.y(bench.pm6.homo) - scale.y(bench.pm6.lumo) - 8), borderColor: "var(--border-strong)" }}
              />
              <div className="absolute w-16 left-4 h-1 rounded bg-[#60A5FA]/60" style={{ top: scale.y(bench.pm6.homo) }} />
              <span className="absolute left-0 w-full text-center text-[9px] mono-num opacity-60" style={{ top: scale.y(bench.pm6.homo) + 6 }}>
                -5.50 / -3.61
              </span>
            </div>

            {/* Y6 Acceptor Benchmark */}
            <div className="absolute left-72 top-0 w-24 opacity-75" style={{ height: scale.H }}>
              <span className="absolute -top-0.5 left-0 w-full text-center text-[10px] font-medium" style={{ color: "var(--text-muted)" }}>
                受体 Y6
              </span>
              <div className="absolute w-16 left-4 h-1 rounded bg-[#F87171]/60" style={{ top: scale.y(bench.y6.lumo) }} />
              <div
                className="absolute left-12 w-1 border-l border-dashed"
                style={{ top: scale.y(bench.y6.lumo) + 4, height: Math.max(6, scale.y(bench.y6.homo) - scale.y(bench.y6.lumo) - 8), borderColor: "var(--border-strong)" }}
              />
              <div className="absolute w-16 left-4 h-1 rounded bg-[#60A5FA]/60" style={{ top: scale.y(bench.y6.homo) }} />
              <span className="absolute left-0 w-full text-center text-[9px] mono-num opacity-60" style={{ top: scale.y(bench.y6.homo) + 6 }}>
                -5.65 / -4.10
              </span>
            </div>
          </div>
        </div>

        {/* Optical Transitions Card */}
        <div
          className="p-3 rounded-xl border space-y-1.5"
          style={{ backgroundColor: "var(--bg-panel)", borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: "var(--text-primary)" }}>
            <Zap size={13} style={{ color: "var(--accent-primary)" }} />
            <span>S0 → S1 理论电子光学跃迁</span>
          </div>
          <div className="text-[11.5px] leading-relaxed flex items-center justify-between">
            <span style={{ color: "var(--text-secondary)" }}>吸收波长 λmax:</span>
            <span className="mono-num font-bold text-[var(--accent-primary)]">
              {s1 ? `${s1.wavelength_nm.toFixed(1)} nm` : "—"}
            </span>
          </div>
          <div className="text-[11.5px] leading-relaxed flex items-center justify-between">
            <span style={{ color: "var(--text-secondary)" }}>振子强度 f:</span>
            <span className="mono-num font-bold text-[var(--text-primary)]">
              {s1 ? s1.oscillator_f.toFixed(3) : "—"}
            </span>
          </div>
          <div className="text-[10.5px] opacity-75 mt-1" style={{ color: "var(--text-muted)" }}>
            注: 扩展休克尔紧束缚 (EHT, 全价电子 s/p/d 基) 对共轭骨架离域体系的快速预测，非 DFT 精度。更精确的激发态与跃迁偶极矩请调用 TD-DFT (ORCA)。
          </div>
        </div>
      </div>
    </FloatingWindow>
  );
};
