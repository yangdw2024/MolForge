import React, { useEffect, useState } from "react";
import { Activity, Play, Search, X } from "lucide-react";
import { molApi } from "../services/api";
import type { AnalysisCatalogItem, AnalysisRunResult } from "../types/molforge";

interface Props {
  open: boolean;
  onClose: () => void;
}

export const AnalysisScienceModal: React.FC<Props> = ({ open, onClose }) => {
  const [items, setItems] = useState<AnalysisCatalogItem[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<AnalysisCatalogItem | null>(null);
  const [result, setResult] = useState<AnalysisRunResult | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!open) return;
    void molApi.getAnalysisCatalog().then((res) => {
      setItems(res.items);
      if (res.items.length && !selected) {
        setSelected(res.items.find((x) => x.state === "Ready") || res.items[0]);
      }
    });
  }, [open]);

  if (!open) return null;

  const filtered = items.filter(
    (it) =>
      !query.trim() ||
      it.title.toLowerCase().includes(query.toLowerCase()) ||
      it.id.toLowerCase().includes(query.toLowerCase()) ||
      it.category.toLowerCase().includes(query.toLowerCase())
  );

  const readyCount = items.filter((x) => x.state === "Ready").length;
  const expCount = items.filter((x) => x.state === "Experimental").length;
  const missCount = items.filter((x) => x.state === "Missing Data").length;

  const runSelected = async () => {
    if (!selected) return;
    setRunning(true);
    try {
      const r = await molApi.runAnalysis(selected.id);
      setResult(r.result);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6" style={{ background: "rgba(3,7,12,0.72)", backdropFilter: "blur(8px)" }}>
      <div
        className="w-full max-w-5xl h-[82vh] rounded-3xl overflow-hidden flex flex-col"
        style={{ background: "var(--md-sys-color-surface)", border: "1px solid var(--md-sys-color-outline-strong)" }}
      >
        <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-2xl flex items-center justify-center" style={{ background: "var(--md-sys-color-primary-container)", color: "var(--md-sys-color-primary)" }}>
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold">MolForge {items.length} 项科研计算与分析入口</h2>
              <p className="text-xs mono-num" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                Ready: {readyCount} · Experimental: {expCount} · Missing Data: {missCount}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl hover:bg-white/5 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 flex min-h-0">
          {/* Catalog List */}
          <div className="w-80 shrink-0 flex flex-col" style={{ borderRight: "1px solid var(--md-sys-color-outline)" }}>
            <div className="p-3" style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}>
              <div className="flex items-center gap-2 rounded-xl px-2.5 py-1.5" style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}>
                <Search className="w-3.5 h-3.5" style={{ color: "var(--md-sys-color-on-surface-muted)" }} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索分析模块 ID / 名称..."
                  className="bg-transparent text-xs outline-none flex-1"
                />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {filtered.map((it) => {
                const active = selected?.id === it.id;
                const badgeColor =
                  it.state === "Ready" ? "#34d399" : it.state === "Missing Data" ? "#f87171" : "#fbbf24";
                return (
                  <button
                    key={it.id}
                    onClick={() => {
                      setSelected(it);
                      setResult(null);
                    }}
                    className="w-full text-left p-2.5 rounded-xl cursor-pointer"
                    style={{
                      background: active ? "var(--md-sys-color-primary-container)" : "transparent",
                    }}
                  >
                    <div className="flex items-center justify-between text-xs font-medium">
                      <span className="truncate">{it.title}</span>
                      <span className="text-[10px] mono-num shrink-0 ml-2" style={{ color: badgeColor }}>
                        {it.state}
                      </span>
                    </div>
                    <div className="text-[10px] mono-num mt-0.5 flex justify-between" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                      <span>{it.id}</span>
                      <span>{it.category}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Inspector & Run View */}
          <div className="flex-1 p-5 overflow-y-auto flex flex-col gap-4">
            {selected ? (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-base font-semibold">{selected.title}</div>
                    <div className="text-xs mt-1" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                      {selected.id} · 引擎: {selected.engine} · {selected.note}
                    </div>
                  </div>
                  <button
                    onClick={() => void runSelected()}
                    disabled={running}
                    className="px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
                    style={{ background: "var(--md-sys-color-primary)", color: "var(--md-sys-color-on-primary)" }}
                  >
                    <Play className="w-3.5 h-3.5" />
                    {running ? "计算中..." : "执行分析"}
                  </button>
                </div>

                {result && (
                  <div className="rounded-2xl p-4 space-y-3" style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}>
                    <div className="text-xs font-semibold" style={{ color: "var(--md-sys-color-primary)" }}>
                      状态: {result.status}
                    </div>
                    <pre className="text-xs whitespace-pre-wrap leading-relaxed" style={{ color: "var(--md-sys-color-on-surface)" }}>
                      {result.summary}
                    </pre>
                    {result.metrics && Object.keys(result.metrics).length > 0 && (
                      <div className="grid grid-cols-3 gap-2 pt-2">
                        {Object.entries(result.metrics).slice(0, 9).map(([k, v]) => (
                          <div key={k} className="rounded-xl p-2" style={{ background: "rgba(0,0,0,0.2)" }}>
                            <div className="text-[10px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>{k}</div>
                            <div className="text-xs mono-num font-medium truncate">{String(v)}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="text-xs" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>请从左侧选择一项科研分析模块</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
