import React, { useState, useRef, useEffect } from "react";
import { Bot, Sparkles, Zap, ArrowRight, CornerDownLeft } from "lucide-react";
import katex from "katex";
import "katex/dist/katex.min.css";
import { useStudioStore } from "../../store/useStudioStore";
import { molApi } from "../../services/api";
import { FloatingWindow } from "./FloatingWindow";

interface AiCopilotLayerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AiCopilotLayer: React.FC<AiCopilotLayerProps> = ({ isOpen, onClose }) => {
  const summary = useStudioStore((s) => s.summary);
  const messages = useStudioStore((s) => s.messages);
  const aiLoading = useStudioStore((s) => s.aiLoading);
  const sendAiPrompt = useStudioStore((s) => s.sendAiPrompt);
  const runTask = useStudioStore((s) => s.runTask);

  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      endRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [isOpen, messages, aiLoading]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || aiLoading) return;
    setInput("");
    void sendAiPrompt(text);
  };

  const handleQuickPrompt = (q: string) => {
    if (aiLoading) return;
    void sendAiPrompt(q);
  };

  const handleBlockAction = (action: string) => {
    if (action === "clean_3d") {
      void runTask("3D 力场优化", () => molApi.clean3D());
    } else if (action === "run_calchem") {
      const ev = new CustomEvent("open-hud-layer", { detail: { layer: "calculation" } });
      window.dispatchEvent(ev);
    } else if (action === "open_qc_modal") {
      const ev = new CustomEvent("open-hud-layer", { detail: { layer: "orbitals" } });
      window.dispatchEvent(ev);
    } else if (action === "export_gjf") {
      void molApi.exportFile("gjf");
    }
  };

  // Render markdown + 真 KaTeX 公式（$...$ 行内 / $$...$$ 独立行）
  const renderMessageContent = (content: string) => {
    const parts = content.split("\n\n");
    return parts.map((part, i) => {
      const rendered = part.split(/(\$\$[^$]+\$\$|\$[^$]+\$)/g).map((seg, j) => {
        if (seg.startsWith("$$") && seg.endsWith("$$")) {
          const html = katex.renderToString(seg.slice(2, -2), { throwOnError: false, displayMode: true });
          return <span key={j} className="block my-1 overflow-x-auto" dangerouslySetInnerHTML={{ __html: html }} />;
        }
        if (seg.startsWith("$") && seg.endsWith("$") && seg.length > 2) {
          const html = katex.renderToString(seg.slice(1, -1), { throwOnError: false, displayMode: false });
          return <span key={j} className="text-[var(--accent-primary)]" dangerouslySetInnerHTML={{ __html: html }} />;
        }
        // bold / inline code formatting
        const boldParts = seg.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((b, k) => {
          if (b.startsWith("**") && b.endsWith("**")) {
            return (
              <strong key={k} className="font-semibold text-[var(--text-primary)]">
                {b.slice(2, -2)}
              </strong>
            );
          }
          if (b.startsWith("`") && b.endsWith("`")) {
            return (
              <code key={k} className="mono-num px-1 rounded bg-[var(--bg-tertiary)] text-[var(--accent-primary)] text-[11px]">
                {b.slice(1, -1)}
              </code>
            );
          }
          return b;
        });
        return <span key={j}>{boldParts}</span>;
      });

      return (
        <p key={i} className="mb-2 leading-relaxed text-[12px] text-[var(--text-secondary)]">
          {rendered}
        </p>
      );
    });
  };

  return (
    <FloatingWindow
      id="ai-copilot-layer"
      title="MolForge AI 科学计算副驾驶 (DeepSeek)"
      icon={<Bot size={15} style={{ color: "var(--accent-primary)" }} />}
      isOpen={isOpen}
      onClose={onClose}
      initialPos={{ x: Math.max(80, window.innerWidth - 680), y: 56 }}
      initialSize={{ width: 460, height: 560 }}
      minWidth={360}
      minHeight={400}
    >
      {/* Active Molecule Context Badges */}
      <div
        className="px-3 py-2 border-b flex flex-wrap items-center gap-1.5 shrink-0"
        style={{
          backgroundColor: "var(--bg-primary)",
          borderColor: "var(--border-subtle)",
        }}
      >
        <span className="text-[10px] uppercase font-bold text-[var(--text-muted)]">上下文:</span>
        <span
          className="text-[10.5px] px-2 py-0.5 rounded-full font-medium"
          style={{ backgroundColor: "var(--accent-soft)", color: "var(--accent-primary)" }}
        >
          {summary?.name || "分子"} · {summary?.formula || ""}
        </span>
        <span
          className="text-[10.5px] px-2 py-0.5 rounded-full font-medium"
          style={{ backgroundColor: "var(--bg-panel)", color: "var(--text-secondary)" }}
        >
          {summary?.num_atoms ?? 0} 原子 / {summary?.num_bonds ?? 0} 键
        </span>
        <span
          className="text-[10.5px] px-2 py-0.5 rounded-full font-medium"
          style={{ backgroundColor: "var(--bg-panel)", color: "var(--text-secondary)" }}
        >
          {summary?.spin_label || "Singlet"}
        </span>
      </div>

      {/* Messages Thread */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
        {messages.length === 0 && (
          <div className="text-center py-6 px-4">
            <div
              className="w-10 h-10 rounded-2xl mx-auto mb-3 flex items-center justify-center border"
              style={{
                backgroundColor: "var(--accent-soft)",
                borderColor: "var(--accent-primary)",
                color: "var(--accent-primary)",
              }}
            >
              <Sparkles size={18} />
            </div>
            <h4 className="font-semibold text-[13px] text-[var(--text-primary)] mb-1">
              你好，我是 MolForge 科学副驾驶
            </h4>
            <p className="text-[11.5px] text-[var(--text-muted)] leading-relaxed max-w-xs mx-auto">
              我已接入当前分子结构。可为您分析轨道能隙、评估 OSC 材料性能、建议 3D 几何优化，或编排科学计算流程。
            </p>

            {/* Quick Prompts */}
            <div className="mt-4 flex flex-wrap justify-center gap-1.5">
              {[
                "分析当前分子的前线轨道与光学能隙",
                "对当前结构执行 3D 力场优化",
                "评估此分子作为有机光伏给体的特性",
                "生成 Gaussian B3LYP 计算输入",
              ].map((qp, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleQuickPrompt(qp)}
                  className="px-2.5 py-1 rounded-lg border text-[11px] text-left hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)] cursor-pointer transition-colors"
                  style={{
                    backgroundColor: "var(--bg-panel)",
                    borderColor: "var(--border-subtle)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {qp}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => {
          const isUser = m.role === "user";
          return (
            <div
              key={m.id}
              className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[90%] p-3 rounded-2xl border ${
                  isUser ? "rounded-br-sm" : "rounded-bl-sm"
                }`}
                style={{
                  backgroundColor: isUser ? "var(--accent-primary)" : "var(--bg-panel)",
                  borderColor: isUser ? "var(--accent-primary)" : "var(--border-subtle)",
                  color: isUser ? "var(--accent-contrast)" : "var(--text-primary)",
                }}
              >
                {renderMessageContent(m.content)}

                {/* Structured A2UI Blocks */}
                {m.a2uiBlocks?.map((b, idx) => {
                  if (b.type === "metrics_card") {
                    return (
                      <div
                        key={idx}
                        className="mt-2.5 p-2 rounded-xl border text-[11px]"
                        style={{ backgroundColor: "var(--bg-primary)", borderColor: "var(--border-subtle)" }}
                      >
                        <div className="font-semibold text-[var(--accent-primary)] mb-1.5">{b.title}</div>
                        <div className="grid grid-cols-2 gap-1.5">
                          {b.items.map((it, k) => (
                            <div key={k} className="flex justify-between">
                              <span className="text-[var(--text-muted)]">{it.label}:</span>
                              <span className="mono-num font-medium text-[var(--text-primary)]">{it.value}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  }
                  if (b.type === "orbital_card") {
                    return (
                      <div
                        key={idx}
                        className="mt-2.5 p-2.5 rounded-xl border"
                        style={{ backgroundColor: "var(--bg-primary)", borderColor: "var(--border-subtle)" }}
                      >
                        <div className="flex items-center gap-1 font-semibold text-[11px] text-[#60A5FA] mb-1.5">
                          <Zap size={12} />
                          <span>{b.title}</span>
                        </div>
                        <div className="grid grid-cols-3 gap-1 text-[11px] mono-num mb-1.5">
                          <div>HOMO: <strong className="text-[#60A5FA]">{b.homo_ev.toFixed(3)}</strong></div>
                          <div>LUMO: <strong className="text-[#F87171]">{b.lumo_ev.toFixed(3)}</strong></div>
                          <div>Eg: <strong className="text-[var(--accent-primary)]">{b.gap_ev.toFixed(3)}</strong></div>
                        </div>
                        {b.s1_text && (
                          <div className="text-[10.5px] text-[var(--text-muted)]">
                            S0 → S1 吸收: <span className="mono-num text-[var(--accent-primary)]">{b.s1_text}</span>
                          </div>
                        )}
                      </div>
                    );
                  }
                  if (b.type === "action_row") {
                    return (
                      <div key={idx} className="mt-2 pt-2 border-t" style={{ borderColor: "var(--border-subtle)" }}>
                        <div className="text-[10.5px] text-[var(--text-muted)] mb-1.5">{b.title}</div>
                        <div className="flex flex-wrap gap-1">
                          {b.actions.map((act, k) => (
                            <button
                              key={k}
                              type="button"
                              onClick={() => handleBlockAction(act.action)}
                              className="px-2.5 py-1 rounded-md text-[11px] font-medium border flex items-center gap-1 cursor-pointer transition-colors hover:bg-[var(--accent-primary)] hover:text-[var(--accent-contrast)]"
                              style={{
                                backgroundColor: "var(--bg-tertiary)",
                                borderColor: "var(--border-subtle)",
                                color: "var(--text-secondary)",
                              }}
                            >
                              <span>{act.label}</span>
                              <ArrowRight size={10} />
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  }
                  return null;
                })}
              </div>
            </div>
          );
        })}

        {aiLoading && (
          <div className="flex items-center gap-2 p-3 rounded-2xl border max-w-[75%]" style={{ backgroundColor: "var(--bg-panel)", borderColor: "var(--border-subtle)" }}>
            <Sparkles size={14} className="animate-spin text-[var(--accent-primary)]" />
            <span className="text-[11.5px] text-[var(--text-muted)]">AI 正在进行前线轨道紧束缚分析与推演...</span>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Input Bar */}
      <div
        className="p-2.5 border-t shrink-0 flex items-center gap-2"
        style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-panel)" }}
      >
        <textarea
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="向 AI 咨询分子性质、3D 优化、或量化方法 (Enter 发送)..."
          className="flex-1 bg-transparent border-0 outline-none resize-none text-[12px] placeholder:text-[var(--text-muted)] max-h-20"
          style={{ color: "var(--text-primary)" }}
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!input.trim() || aiLoading}
          className="w-7 h-7 rounded-lg flex items-center justify-center cursor-pointer transition-opacity disabled:opacity-30"
          style={{ backgroundColor: "var(--accent-primary)", color: "var(--accent-contrast)" }}
          title="发送"
        >
          <CornerDownLeft size={13} />
        </button>
      </div>
    </FloatingWindow>
  );
};
