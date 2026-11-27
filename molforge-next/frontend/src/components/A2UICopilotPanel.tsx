import React, { useState } from "react";
import { Atom, Bot, Send, Sparkles, Zap } from "lucide-react";
import type { A2UIBlock, Atom2DItem, ChatMessage, DocumentSummary } from "../types/molforge";

interface Props {
  summary: DocumentSummary | null;
  atoms2d: Atom2DItem[];
  selectedIndices: number[];
  messages: ChatMessage[];
  aiLoading: boolean;
  onSendPrompt: (text: string) => void;
  onClearMessages: () => void;
  onAction: (action: string) => void;
  onDeleteSelected: () => void;
  onSetChargeSpin: (charge: number, mult: number) => void;
}

const renderRichInline = (text: string): React.ReactNode => {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold" style={{ color: "var(--md-sys-color-primary)" }}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={i}
          className="mono-num px-1 py-0.5 rounded text-[11px]"
          style={{ background: "rgba(94, 234, 212, 0.12)", color: "var(--md-sys-color-primary)" }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
};

const A2UIBlockView: React.FC<{ block: A2UIBlock; onAction: (action: string) => void }> = ({ block, onAction }) => {
  if (block.type === "metrics_card") {
    return (
      <div
        className="rounded-2xl p-3 mt-2"
        style={{
          background: "var(--md-sys-color-surface-highest)",
          border: "1px solid var(--md-sys-color-outline)",
        }}
      >
        <div className="text-[11px] font-semibold mb-2 flex items-center gap-1.5" style={{ color: "var(--md-sys-color-primary)" }}>
          <Atom className="w-3.5 h-3.5" />
          {block.title}
        </div>
        <div className="grid grid-cols-2 gap-2">
          {block.items.map((it) => (
            <div key={it.label} className="rounded-xl px-2.5 py-1.5" style={{ background: "rgba(0,0,0,0.18)" }}>
              <div className="text-[10px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                {it.label}
              </div>
              <div className="text-[11px] font-medium mono-num break-words leading-snug">{it.value}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (block.type === "orbital_card") {
    return (
      <div
        className="rounded-2xl p-3 mt-2"
        style={{
          background: "var(--md-sys-color-surface-highest)",
          border: "1px solid var(--md-sys-color-outline-strong)",
        }}
      >
        <div className="text-[11px] font-semibold mb-2 flex items-center justify-between">
          <span className="flex items-center gap-1.5" style={{ color: "var(--md-sys-color-primary)" }}>
            <Zap className="w-3.5 h-3.5" />
            {block.title}
          </span>
          <span className="mono-num text-[10px] px-2 py-0.5 rounded-full" style={{ background: "var(--md-sys-color-primary-container)", color: "var(--md-sys-color-primary)" }}>
            Eg = {block.gap_ev.toFixed(2)} eV
          </span>
        </div>
        <div className="flex items-center justify-between text-xs mono-num mb-1.5">
          <span>
            LUMO <b style={{ color: "var(--md-sys-color-tertiary)" }}>{block.lumo_ev.toFixed(3)} eV</b>
          </span>
          <span>
            HOMO <b style={{ color: "var(--md-sys-color-secondary)" }}>{block.homo_ev.toFixed(3)} eV</b>
          </span>
        </div>
        <div className="w-full h-2 rounded-full overflow-hidden flex" style={{ background: "rgba(0,0,0,0.3)" }}>
          <div className="h-full" style={{ width: "44%", background: "var(--md-sys-color-secondary)" }} />
          <div className="h-full flex-1" style={{ background: "transparent" }} />
          <div className="h-full" style={{ width: "26%", background: "var(--md-sys-color-tertiary)" }} />
        </div>
        <div className="text-[10px] mt-1.5 mono-num" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
          预测 S₀→S₁: {block.s1_text}
        </div>
      </div>
    );
  }

  if (block.type === "action_row") {
    return (
      <div className="mt-2 flex flex-wrap gap-1.5">
        {block.actions.map((act) => (
          <button
            key={act.action}
            onClick={() => onAction(act.action)}
            className="m3-spring text-[11px] font-medium px-2.5 py-1 rounded-full cursor-pointer hover:scale-[1.03]"
            style={{
              background: "var(--md-sys-color-primary-container)",
              color: "var(--md-sys-color-primary)",
              border: "1px solid var(--md-sys-color-outline-strong)",
            }}
          >
            {act.label}
          </button>
        ))}
      </div>
    );
  }

  return null;
};

export const A2UICopilotPanel: React.FC<Props> = ({
  summary,
  atoms2d,
  selectedIndices,
  messages,
  aiLoading,
  onSendPrompt,
  onClearMessages,
  onAction,
  onDeleteSelected,
  onSetChargeSpin,
}) => {
  const [input, setInput] = useState("");
  const selectedAtom = selectedIndices.length === 1 ? atoms2d[selectedIndices[0]] : undefined;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = input.trim();
    if (!t || aiLoading) return;
    setInput("");
    onSendPrompt(t);
  };

  return (
    <aside
      className="w-[340px] shrink-0 h-full flex flex-col"
      style={{
        background: "var(--md-sys-color-surface-low)",
        borderLeft: "1px solid var(--md-sys-color-outline)",
      }}
    >
      {/* Selected Atom / Structure Inspector Card */}
      <div className="p-3.5" style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold tracking-wide">属性检查器 · INSPECTOR</span>
          {selectedIndices.length > 0 && (
            <button
              onClick={onDeleteSelected}
              className="text-[11px] px-2 py-0.5 rounded-lg cursor-pointer"
              style={{ background: "rgba(248, 113, 113, 0.16)", color: "#f87171" }}
            >
              删除选中 ({selectedIndices.length})
            </button>
          )}
        </div>

        {selectedAtom ? (
          <div className="rounded-2xl p-2.5 text-xs space-y-1.5" style={{ background: "rgba(0,0,0,0.18)" }}>
            <div className="flex items-center justify-between">
              <span className="font-semibold">
                原子 #{selectedAtom.display_id} · {selectedAtom.symbol}
              </span>
              <span className="mono-num text-[11px]" style={{ color: "var(--md-sys-color-primary)" }}>
                Z={selectedAtom.atomic_num}
              </span>
            </div>
            <div className="mono-num text-[11px] grid grid-cols-3 gap-1" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
              <span>X {selectedAtom.x.toFixed(3)}</span>
              <span>Y {selectedAtom.y.toFixed(3)}</span>
              <span>Z {selectedAtom.z.toFixed(3)}</span>
            </div>
          </div>
        ) : (
          <div className="rounded-2xl p-2.5 text-xs space-y-1" style={{ background: "rgba(0,0,0,0.14)" }}>
            <div className="flex justify-between">
              <span style={{ color: "var(--md-sys-color-on-surface-muted)" }}>对称 / 形态</span>
              <span className="mono-num">{summary?.geometry_label || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--md-sys-color-on-surface-muted)" }}>自旋电子态</span>
              <span className="mono-num">{summary?.spin_label || "—"}</span>
            </div>
            <div className="flex justify-between items-center">
              <span style={{ color: "var(--md-sys-color-on-surface-muted)" }}>电荷 / 多重度</span>
              <span className="mono-num flex items-center gap-1.5">
                <button
                  onClick={() => summary && onSetChargeSpin(summary.charge - 1, summary.multiplicity)}
                  className="px-1.5 rounded bg-white/5 cursor-pointer"
                >
                  -
                </button>
                <span>Q={summary?.charge ?? 0}</span>
                <button
                  onClick={() => summary && onSetChargeSpin(summary.charge + 1, summary.multiplicity)}
                  className="px-1.5 rounded bg-white/5 cursor-pointer"
                >
                  +
                </button>
                <span>M={summary?.multiplicity ?? 1}</span>
              </span>
            </div>
            {summary?.cell && (
              <div className="flex justify-between">
                <span style={{ color: "var(--md-sys-color-on-surface-muted)" }}>晶胞参数 (Å)</span>
                <span className="mono-num">
                  {summary.cell.a.toFixed(1)}×{summary.cell.b.toFixed(1)}×{summary.cell.c.toFixed(1)}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Google A2UI Declarative Copilot Stream */}
      <div className="flex-1 flex flex-col min-h-0">
        <div className="px-3.5 py-2.5 flex items-center justify-between" style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}>
          <div className="flex items-center gap-2">
            <div
              className="w-6 h-6 rounded-lg flex items-center justify-center"
              style={{ background: "var(--md-sys-color-primary-container)", color: "var(--md-sys-color-primary)" }}
            >
              <Bot className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-xs font-semibold leading-none">AI 科研副驾驶</div>
              <div className="text-[10px] mt-0.5" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                Google A2UI Cards
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={onClearMessages}
              className="text-[10px] px-2 py-1 rounded-full cursor-pointer hover:bg-white/5"
              style={{ color: "var(--md-sys-color-on-surface-muted)" }}
            >
              清空
            </button>
            <button
              onClick={() => onAction("open_qc_modal")}
              className="text-[11px] px-2.5 py-1 rounded-full font-medium cursor-pointer flex items-center gap-1"
              style={{ background: "var(--md-sys-color-primary-container)", color: "var(--md-sys-color-primary)" }}
            >
              <Sparkles className="w-3 h-3" />
              能级图
            </button>
          </div>
        </div>

        {/* Quick prompts */}
        <div className="px-3 py-2 flex flex-wrap gap-1.5" style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}>
          {["分析当前分子前线轨道", "构建五并苯半导体", "生成阿司匹林分子"].map((q) => (
            <button
              key={q}
              onClick={() => onSendPrompt(q)}
              className="m3-spring text-[10px] px-2 py-1 rounded-full cursor-pointer"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--md-sys-color-outline)",
                color: "var(--md-sys-color-on-surface-muted)",
              }}
            >
              {q}
            </button>
          ))}
        </div>

        {/* Chat stream */}
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {messages.map((m) => (
            <div key={m.id} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
              <div
                className="max-w-[95%] rounded-2xl px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap"
                style={{
                  background: m.role === "user" ? "var(--md-sys-color-primary)" : "rgba(255,255,255,0.04)",
                  color: m.role === "user" ? "var(--md-sys-color-on-primary)" : "var(--md-sys-color-on-surface)",
                  border: m.role === "assistant" ? "1px solid var(--md-sys-color-outline)" : "none",
                }}
              >
                {m.role === "assistant" ? renderRichInline(m.content) : m.content}
                {m.a2uiBlocks?.map((blk, idx) => (
                  <A2UIBlockView key={idx} block={blk} onAction={onAction} />
                ))}
              </div>
            </div>
          ))}
          {aiLoading && (
            <div className="text-xs px-2 py-1 animate-pulse" style={{ color: "var(--md-sys-color-primary)" }}>
              正在求解电子结构并生成 A2UI 卡片...
            </div>
          )}
        </div>

        <form onSubmit={submit} className="p-3" style={{ borderTop: "1px solid var(--md-sys-color-outline)" }}>
          <div
            className="flex items-center gap-1.5 rounded-2xl px-2.5 py-1.5"
            style={{ background: "var(--md-sys-color-surface)", border: "1px solid var(--md-sys-color-outline)" }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入分子指令、能级对比或结构修改..."
              className="flex-1 bg-transparent text-xs outline-none"
              style={{ color: "var(--md-sys-color-on-surface)" }}
            />
            <button
              type="submit"
              disabled={aiLoading}
              className="w-7 h-7 rounded-xl flex items-center justify-center cursor-pointer m3-spring"
              style={{ background: "var(--md-sys-color-primary)", color: "var(--md-sys-color-on-primary)" }}
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </form>
      </div>
    </aside>
  );
};
