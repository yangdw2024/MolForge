import React, { useMemo, useRef, useState } from "react";
import { Bot, Info, Minus, Plus, Send, Sparkles, Trash2, X } from "lucide-react";
import { molApi } from "../../services/api";
import { useStudioStore } from "../../store/useStudioStore";
import type { Preview2DStructure } from "../../types/studio";
import { StructureThumbnail2D } from "../common/StructureThumbnail2D";

export const InspectorPanel: React.FC = () => {
  const inspectorOpen = useStudioStore((s) => s.inspectorOpen);
  const inspectorWidth = useStudioStore((s) => s.inspectorWidth);
  const setInspectorWidth = useStudioStore((s) => s.setInspectorWidth);
  const summary = useStudioStore((s) => s.summary);
  const atoms2d = useStudioStore((s) => s.atoms2d);
  const elements = useStudioStore((s) => s.elements);
  const selectedIndices = useStudioStore((s) => s.selectedIndices);
  const projectPath = useStudioStore((s) => s.projectPath);
  const runTask = useStudioStore((s) => s.runTask);
  const aiDrawerOpen = useStudioStore((s) => s.aiDrawerOpen);
  const setAiDrawerOpen = useStudioStore((s) => s.setAiDrawerOpen);
  const setInspectorOpen = useStudioStore((s) => s.setInspectorOpen);
  const messages = useStudioStore((s) => s.messages);
  const aiLoading = useStudioStore((s) => s.aiLoading);
  const sendAiPrompt = useStudioStore((s) => s.sendAiPrompt);
  const setRoute = useStudioStore((s) => s.setRoute);

  const [promptInput, setPromptInput] = useState("");
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);

  const preview2d = useMemo<Preview2DStructure | null>(() => {
    if (!atoms2d || atoms2d.truncated || atoms2d.atoms.length === 0) return null;
    return {
      atoms: atoms2d.atoms.map((a) => ({
        index: a.index,
        symbol: a.symbol,
        atomic_num: a.atomic_num,
        x2: a.x2,
        y2: a.y2,
        color: a.color,
      })),
      bonds: atoms2d.bonds.map((b) => ({
        i: b.i,
        j: b.j,
        order: b.order,
        aromatic: b.aromatic,
      })),
    };
  }, [atoms2d]);

  const selectedAtomDetails = useMemo(() => {
    if (!atoms2d || selectedIndices.length === 0) return [];
    return selectedIndices
      .map((idx) => atoms2d.atoms[idx])
      .filter(Boolean)
      .slice(0, 6);
  }, [atoms2d, selectedIndices]);

  if (!inspectorOpen) return null;

  const firstEl = selectedAtomDetails[0]
    ? elements.find((e) => e.atomic_number === selectedAtomDetails[0].atomic_num)
    : undefined;

  return (
    <aside
      data-testid="inspector-panel"
      className="absolute top-3 right-3 bottom-3 z-30 rounded-2xl border flex flex-col min-h-0 overflow-hidden backdrop-blur-xl"
      style={{
        width: inspectorWidth,
        backgroundColor: "color-mix(in srgb, var(--bg-secondary) 86%, transparent)",
        borderColor: "var(--border-subtle)",
        boxShadow: "0 20px 50px rgba(0, 0, 0, 0.38)",
      }}
    >
      {/* Left resize handle */}
      <div
        role="separator"
        aria-orientation="vertical"
        onMouseDown={(e) => {
          dragRef.current = { startX: e.clientX, startW: inspectorWidth };
          const onMove = (ev: MouseEvent) => {
            if (!dragRef.current) return;
            setInspectorWidth(dragRef.current.startW + (dragRef.current.startX - ev.clientX));
          };
          const onUp = () => {
            dragRef.current = null;
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
          };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        }}
        className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-[var(--accent-primary)] transition-colors z-10"
      />

      {/* Inspector / Copilot Tabs + Close */}
      <div className="px-3 pt-2.5 pb-2 border-b flex items-center gap-1.5" style={{ borderColor: "var(--border-subtle)" }}>
        <button
          type="button"
          onClick={() => setAiDrawerOpen(false)}
          className="flex-1 h-7 rounded-md text-[12px] font-medium flex items-center justify-center gap-1.5 cursor-pointer"
          style={{
            backgroundColor: !aiDrawerOpen ? "var(--accent-soft)" : "transparent",
            color: !aiDrawerOpen ? "var(--accent-primary)" : "var(--text-secondary)",
          }}
        >
          <Info size={13} />
          <span>属性检查器</span>
        </button>
        <button
          type="button"
          onClick={() => setAiDrawerOpen(true)}
          className="flex-1 h-7 rounded-md text-[12px] font-medium flex items-center justify-center gap-1.5 cursor-pointer"
          style={{
            backgroundColor: aiDrawerOpen ? "var(--accent-soft)" : "transparent",
            color: aiDrawerOpen ? "var(--accent-primary)" : "var(--text-secondary)",
          }}
        >
          <Bot size={13} />
          <span>AI 科研副驾驶</span>
        </button>
        <button
          type="button"
          onClick={() => setInspectorOpen(false)}
          title="收起悬浮图层"
          className="h-7 w-7 rounded-md flex items-center justify-center cursor-pointer hover:opacity-80"
          style={{ color: "var(--text-muted)" }}
        >
          <X size={14} />
        </button>
      </div>

      {!aiDrawerOpen ? (
        <div className="flex-1 studio-scroll p-3 space-y-3">
          {/* 2D Structure Mini Preview */}
          <div className="studio-surface p-2.5 flex flex-col items-center">
            <div className="w-full flex items-center justify-between mb-1.5">
              <span className="text-[11px] font-semibold" style={{ color: "var(--text-secondary)" }}>
                结构二维预览
              </span>
              {summary?.formula && (
                <span className="mono-num text-[11px]" style={{ color: "var(--accent-primary)" }}>
                  {summary.formula}
                </span>
              )}
            </div>
            {preview2d ? (
              <StructureThumbnail2D preview={preview2d} width={Math.max(180, inspectorWidth - 52)} height={116} />
            ) : (
              <div className="py-5 text-[11.5px] text-center" style={{ color: "var(--text-muted)" }}>
                {atoms2d?.truncated ? `大体系 (${atoms2d.num_atoms.toLocaleString()} 原子) 已省略 2D 缩略图` : "当前无活动结构"}
              </div>
            )}
          </div>

          {/* Core Telemetry */}
          {summary && (
            <div className="studio-surface p-3 space-y-2 text-[12px]">
              <div className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                物理与拓扑指标
              </div>
              <div className="grid grid-cols-2 gap-y-1.5 gap-x-2">
                <span style={{ color: "var(--text-secondary)" }}>分子量</span>
                <span className="mono-num text-right font-medium">
                  {summary.molecular_weight != null ? `${summary.molecular_weight} Da` : "—"}
                </span>
                <span style={{ color: "var(--text-secondary)" }}>原子 / 键数</span>
                <span className="mono-num text-right">
                  {summary.num_atoms.toLocaleString()} / {summary.num_bonds.toLocaleString()}
                </span>
                <span style={{ color: "var(--text-secondary)" }}>几何形态</span>
                <span className="text-right truncate" title={summary.geometry_label}>
                  {summary.geometry_label}
                </span>
                <span style={{ color: "var(--text-secondary)" }}>点群</span>
                <span className="mono-num text-right">{summary.point_group}</span>
                <span style={{ color: "var(--text-secondary)" }}>自旋态</span>
                <span className="text-right">{summary.spin_label}</span>
              </div>

              {/* Charge & Spin */}
              <div className="pt-2 border-t flex items-center justify-between" style={{ borderColor: "var(--border-subtle)" }}>
                <span style={{ color: "var(--text-secondary)" }}>净电荷 Q / M</span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    className="studio-btn !h-6 !w-6 !p-0"
                    onClick={() => void runTask("调整净电荷", () => molApi.setChargeSpin(summary.charge - 1, summary.multiplicity))}
                    title="减少总电荷"
                  >
                    <Minus size={11} />
                  </button>
                  <span className="mono-num px-1.5 text-[11.5px]">
                    {summary.charge >= 0 ? `+${summary.charge}` : summary.charge} / {summary.multiplicity}
                  </span>
                  <button
                    type="button"
                    className="studio-btn !h-6 !w-6 !p-0"
                    onClick={() => void runTask("调整净电荷", () => molApi.setChargeSpin(summary.charge + 1, summary.multiplicity))}
                    title="增加总电荷"
                  >
                    <Plus size={11} />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Unit Cell if present */}
          {summary?.cell && (
            <div className="studio-surface p-3 space-y-1.5 text-[12px]">
              <div className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                晶胞参数 (CRYST1)
              </div>
              <div className="mono-num text-[11.5px]" style={{ color: "var(--text-primary)" }}>
                a={summary.cell.a.toFixed(2)} Å, b={summary.cell.b.toFixed(2)} Å, c={summary.cell.c.toFixed(2)} Å
              </div>
              <div className="mono-num text-[11px]" style={{ color: "var(--text-secondary)" }}>
                α={summary.cell.alpha.toFixed(1)}° β={summary.cell.beta.toFixed(1)}° γ={summary.cell.gamma.toFixed(1)}°
              </div>
            </div>
          )}

          {/* Selected Atom Details */}
          <div className="studio-surface p-3 space-y-2 text-[12px]">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                选中对象 ({selectedIndices.length})
              </span>
              {selectedAtomDetails.length > 0 && (
                <button
                  type="button"
                  className="text-[11px] flex items-center gap-1 cursor-pointer hover:underline"
                  style={{ color: "var(--semantic-error)" }}
                  onClick={() => void runTask("删除选中原子", () => molApi.deleteIndices(selectedIndices))}
                >
                  <Trash2 size={11} />
                  删除
                </button>
              )}
            </div>

            {selectedAtomDetails.length === 0 ? (
              <div className="text-[11.5px]" style={{ color: "var(--text-muted)" }}>
                在 2D 画布或 3D 视口中点击原子，查看实测坐标与元素参数。
              </div>
            ) : (
              <div className="space-y-2">
                {selectedAtomDetails.map((a) => (
                  <div key={a.atom_id} className="studio-inset p-2 text-[11.5px] space-y-1">
                    <div className="flex items-center justify-between font-semibold">
                      <span>
                        #{a.display_id} {a.symbol} (Z={a.atomic_num})
                      </span>
                      <span className="mono-num text-[11px]" style={{ color: "var(--text-muted)" }}>
                        q={a.formal_charge}
                      </span>
                    </div>
                    <div className="mono-num text-[11px]" style={{ color: "var(--text-secondary)" }}>
                      ({a.x.toFixed(3)}, {a.y.toFixed(3)}, {a.z.toFixed(3)}) Å
                    </div>
                  </div>
                ))}
                {firstEl && (
                  <div className="text-[11px] space-y-0.5 pt-1" style={{ color: "var(--text-secondary)" }}>
                    <div>{firstEl.name_cn} ({firstEl.name}) · {firstEl.category}</div>
                    <div className="mono-num">
                      VdW {firstEl.vdw_radius} Å · 共价 {firstEl.covalent_radius} Å · χ={firstEl.electronegativity ?? "—"}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Provenance / Source Path */}
          <div className="studio-surface p-3 text-[11.5px] space-y-1">
            <div className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              数据来源
            </div>
            <div className="mono-num break-all text-[11px]" style={{ color: "var(--text-secondary)" }}>
              {projectPath || summary?.source_path || "内存实时构建 / 预设体系"}
            </div>
          </div>
        </div>
      ) : (
        /* Embedded AI Copilot Drawer */
        <div className="flex-1 flex flex-col min-h-0">
          <div className="px-3 py-2 border-b flex items-center justify-between text-[11px]" style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}>
            <span className="flex items-center gap-1">
              <Sparkles size={12} style={{ color: "var(--accent-primary)" }} />
              A2UI 科研副驾驶
            </span>
            <button
              type="button"
              className="hover:underline cursor-pointer"
              style={{ color: "var(--accent-primary)" }}
              onClick={() => setRoute("analysis")}
            >
              打开能级图 →
            </button>
          </div>

          <div className="flex-1 studio-scroll p-3 space-y-2.5">
            {messages.map((m) => (
              <div
                key={m.id}
                className="rounded-lg p-2.5 text-[12px] space-y-2"
                style={{
                  backgroundColor: m.role === "user" ? "var(--accent-soft)" : "var(--bg-panel)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <div className="whitespace-pre-wrap" style={{ color: "var(--text-primary)", userSelect: "text" }}>
                  {m.content}
                </div>
                {m.a2uiBlocks?.map((blk, i) => {
                  if (blk.type === "metrics_card") {
                    return (
                      <div key={i} className="studio-inset p-2 space-y-1">
                        <div className="text-[11px] font-semibold" style={{ color: "var(--accent-primary)" }}>
                          {blk.title}
                        </div>
                        <div className="grid grid-cols-2 gap-1 text-[11px]">
                          {blk.items.map((it, j) => (
                            <div key={j} className="flex justify-between gap-1">
                              <span style={{ color: "var(--text-muted)" }}>{it.label}</span>
                              <span className="mono-num">{it.value}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  }
                  if (blk.type === "orbital_card") {
                    return (
                      <div key={i} className="studio-inset p-2 space-y-1 text-[11px]">
                        <div className="font-semibold" style={{ color: "var(--semantic-info)" }}>
                          {blk.title}
                        </div>
                        <div className="mono-num flex justify-between">
                          <span>HOMO {blk.homo_ev} eV</span>
                          <span>LUMO {blk.lumo_ev} eV</span>
                          <span>Eg {blk.gap_ev} eV</span>
                        </div>
                      </div>
                    );
                  }
                  return null;
                })}
              </div>
            ))}
          </div>

          <form
            className="p-2.5 border-t flex gap-1.5"
            style={{ borderColor: "var(--border-subtle)" }}
            onSubmit={(e) => {
              e.preventDefault();
              if (!promptInput.trim()) return;
              const q = promptInput;
              setPromptInput("");
              void sendAiPrompt(q);
            }}
          >
            <input
              type="text"
              value={promptInput}
              onChange={(e) => setPromptInput(e.target.value)}
              placeholder="输入科研问题或结构指令..."
              className="studio-input flex-1"
              disabled={aiLoading}
            />
            <button type="submit" className="studio-btn studio-btn-primary !px-2.5" disabled={aiLoading}>
              <Send size={13} />
            </button>
          </form>
        </div>
      )}
    </aside>
  );
};
