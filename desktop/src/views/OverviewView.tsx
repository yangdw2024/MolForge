import React, { useState } from "react";
import {
  ArrowUpRight,
  Atom,
  Database,
  FilePlus2,
  FlaskConical,
  FolderOpen,
  History,
  Layers,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import { molApi } from "../services/api";
import { useStudioStore } from "../store/useStudioStore";
import { StructureThumbnail2D } from "../components/common/StructureThumbnail2D";

export const OverviewView: React.FC = () => {
  const summary = useStudioStore((s) => s.summary);
  const libraryItems = useStudioStore((s) => s.libraryItems);
  const recentProjects = useStudioStore((s) => s.recentProjects);
  const recentAnalyses = useStudioStore((s) => s.recentAnalyses);
  const recoveryPrompt = useStudioStore((s) => s.recoveryPrompt);
  const bridgeConnected = useStudioStore((s) => s.bridgeConnected);
  const openStructureDialog = useStudioStore((s) => s.openStructureDialog);
  const openProjectDialog = useStudioStore((s) => s.openProjectDialog);
  const openFilePath = useStudioStore((s) => s.openFilePath);
  const restoreAutosave = useStudioStore((s) => s.restoreAutosave);
  const dismissAutosave = useStudioStore((s) => s.dismissAutosave);
  const runTask = useStudioStore((s) => s.runTask);
  const setRoute = useStudioStore((s) => s.setRoute);

  const [quickSmiles, setQuickSmiles] = useState("");

  return (
    <div data-testid="view-overview" className="h-full studio-scroll p-5 space-y-5">
      {/* Recovery Banner */}
      {recoveryPrompt?.available && (
        <div
          className="studio-surface px-4 py-3 flex flex-wrap items-center justify-between gap-3"
          style={{
            borderColor: "var(--semantic-warning)",
            backgroundColor: "var(--semantic-warning-soft)",
          }}
        >
          <div className="flex items-center gap-2.5 text-[12.5px]">
            <RotateCcw size={16} style={{ color: "var(--semantic-warning)" }} />
            <div>
              <span className="font-semibold">检测到上次未提交的自动备份工程：</span>
              <span className="mono-num">
                {recoveryPrompt.name || "Untitled"} ({recoveryPrompt.formula || "—"}) · 保存于{" "}
                {recoveryPrompt.savedAt ? new Date(recoveryPrompt.savedAt).toLocaleString("zh-CN") : ""}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => void restoreAutosave()} className="studio-btn studio-btn-primary !h-7">
              一键恢复会话
            </button>
            <button type="button" onClick={() => void dismissAutosave()} className="studio-btn !h-7 !w-7 !p-0">
              <X size={13} />
            </button>
          </div>
        </div>
      )}

      {/* Scientific Hero Launchpad */}
      <section className="studio-surface p-5 relative overflow-hidden">
        <svg
          className="absolute right-4 top-2 opacity-[0.06] pointer-events-none"
          width="220"
          height="140"
          viewBox="0 0 220 140"
          fill="none"
          aria-hidden="true"
        >
          <polygon points="50,15 80,32 80,67 50,84 20,67 20,32" stroke="currentColor" strokeWidth="2.5" />
          <polygon points="110,15 140,32 140,67 110,84 80,67 80,32" stroke="currentColor" strokeWidth="2.5" />
          <polygon points="170,15 200,32 200,67 170,84 140,67 140,32" stroke="currentColor" strokeWidth="2.5" />
          <polygon points="80,67 110,84 110,119 80,136 50,119 50,84" stroke="currentColor" strokeWidth="2.5" />
          <polygon points="140,67 170,84 170,119 140,136 110,119 110,84" stroke="currentColor" strokeWidth="2.5" />
        </svg>

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1.5 max-w-2xl">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--accent-primary)" }}>
              <span>MolForge Studio · Scientific Workstation</span>
              <span className="mono-num px-1.5 py-0.5 rounded" style={{ backgroundColor: "var(--accent-soft)" }}>
                {bridgeConnected ? "Engine Ready" : "Offline"}
              </span>
            </div>
            <h1 className="text-[20px] font-semibold tracking-tight">
              2D/3D 分子建模、有机半导体与量化科研工作站
            </h1>
            <p className="text-[12.5px]" style={{ color: "var(--text-secondary)" }}>
              基于真实 RDKit 拓扑、CommandBus 原子级事务栈、32 万原子 WebGPU 渲染管线及 79 项分析引擎。
            </p>
          </div>

          {/* Quick SMILES Input */}
          <form
            className="flex items-center gap-2 shrink-0"
            onSubmit={(e) => {
              e.preventDefault();
              const s = quickSmiles.trim();
              if (!s) return;
              void runTask(`生成 ${s}`, () => molApi.buildSmiles(s, s), true);
              setQuickSmiles("");
            }}
          >
            <input
              type="text"
              value={quickSmiles}
              onChange={(e) => setQuickSmiles(e.target.value)}
              placeholder="快速输入 SMILES 生成三维结构 (如 c1ccccc1)..."
              className="studio-input w-[280px] mono-num"
            />
            <button type="submit" className="studio-btn studio-btn-primary">
              <FilePlus2 size={13.5} />
              <span>新建体系</span>
            </button>
          </form>
        </div>

        {/* Action Strip */}
        <div className="relative z-10 mt-4 pt-3.5 border-t flex flex-wrap items-center gap-2" style={{ borderColor: "var(--border-subtle)" }}>
          <button type="button" onClick={() => void openProjectDialog()} className="studio-btn">
            <FolderOpen size={13.5} style={{ color: "var(--accent-primary)" }} />
            <span>打开 .mforge 工程</span>
          </button>
          <button type="button" onClick={() => void openStructureDialog()} className="studio-btn">
            <Atom size={13.5} />
            <span>导入结构 (.pdb / .xyz / .mol / .cif)</span>
          </button>
          <button type="button" onClick={() => setRoute("editor")} className="studio-btn">
            <ArrowUpRight size={13.5} />
            <span>进入当前编辑器 ({summary?.name || "咖啡因"})</span>
          </button>
          <button type="button" onClick={() => setRoute("analysis")} className="studio-btn">
            <FlaskConical size={13.5} />
            <span>分析与能级工作台</span>
          </button>
          <button
            type="button"
            onClick={() => void openFilePath("E:\\YDW\\test_wsl\\ydw-PM6-ClFFCl.pdb")}
            className="studio-btn"
            title="加载 321,554 原子大体系测试晶体框与 GPU 性能"
          >
            <Sparkles size={13.5} style={{ color: "var(--semantic-info)" }} />
            <span>32 万原子 WebGPU 实测体系</span>
          </button>
        </div>
      </section>

      {/* Three Functional Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Column 1: Recent Projects */}
        <section className="studio-surface p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[13px] font-semibold flex items-center gap-1.5">
              <History size={14} style={{ color: "var(--accent-primary)" }} />
              <span>最近打开的工程与结构</span>
            </h2>
            <span className="mono-num text-[11px]" style={{ color: "var(--text-muted)" }}>
              {recentProjects.length}
            </span>
          </div>

          {recentProjects.length === 0 ? (
            <div className="studio-inset p-4 text-[12px] space-y-1.5" style={{ color: "var(--text-secondary)" }}>
              <div>暂无本地最近工程记录。</div>
              <div style={{ color: "var(--text-muted)" }}>
                保存 `.mforge` 工程或导入本地 `.pdb`/`.xyz` 文件后，此处会自动显示并支持一键恢复。
              </div>
            </div>
          ) : (
            <div className="space-y-1.5">
              {recentProjects.slice(0, 6).map((rp) => (
                <button
                  key={rp.path}
                  type="button"
                  onClick={() => void openFilePath(rp.path)}
                  className="w-full studio-inset p-2.5 text-left hover:border-[var(--accent-primary)] transition-colors cursor-pointer"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12.5px] font-medium truncate">{rp.name}</span>
                    {rp.formula && (
                      <span className="mono-num text-[11px]" style={{ color: "var(--accent-primary)" }}>
                        {rp.formula}
                      </span>
                    )}
                  </div>
                  <div className="mono-num text-[10.5px] truncate mt-0.5" style={{ color: "var(--text-muted)" }}>
                    {rp.path}
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Column 2: Sample Datasets */}
        <section className="studio-surface p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[13px] font-semibold flex items-center gap-1.5">
              <Database size={14} style={{ color: "var(--accent-primary)" }} />
              <span>示例科研分子体系</span>
            </h2>
            <button
              type="button"
              onClick={() => setRoute("library")}
              className="text-[11.5px] hover:underline cursor-pointer"
              style={{ color: "var(--accent-primary)" }}
            >
              全部分子库 →
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {libraryItems.slice(0, 4).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => void runTask(`载入 ${item.name}`, () => molApi.loadPreset(item.id), true)}
                className="studio-inset p-2 flex flex-col items-center hover:border-[var(--accent-primary)] transition-colors cursor-pointer"
              >
                <StructureThumbnail2D preview={item.preview_2d} width={116} height={64} />
                <div className="w-full mt-1 flex items-center justify-between gap-1 text-[11.5px]">
                  <span className="font-medium truncate">{item.name}</span>
                  <span className="mono-num text-[10.5px]" style={{ color: "var(--text-muted)" }}>
                    {item.formula}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* Column 3: Recent Analyses & Workflows */}
        <section className="studio-surface p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[13px] font-semibold flex items-center gap-1.5">
              <Layers size={14} style={{ color: "var(--accent-primary)" }} />
              <span>常用科研流水线与记录</span>
            </h2>
            <button
              type="button"
              onClick={() => setRoute("jobs")}
              className="text-[11.5px] hover:underline cursor-pointer"
              style={{ color: "var(--accent-primary)" }}
            >
              任务中心 →
            </button>
          </div>

          <div className="space-y-1.5">
            <button
              type="button"
              onClick={() => setRoute("analysis")}
              className="w-full studio-inset p-2.5 flex items-center justify-between hover:border-[var(--accent-primary)] cursor-pointer text-left"
            >
              <div>
                <div className="text-[12px] font-medium">OSC 前线轨道紧束缚筛选</div>
                <div className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  计算 HOMO / LUMO / Eg 并对比 PM6 & Y6 受体
                </div>
              </div>
              <ArrowUpRight size={13.5} style={{ color: "var(--text-muted)" }} />
            </button>

            <button
              type="button"
              onClick={() => setRoute("reports")}
              className="w-full studio-inset p-2.5 flex items-center justify-between hover:border-[var(--accent-primary)] cursor-pointer text-left"
            >
              <div>
                <div className="text-[12px] font-medium">导出 Gaussian (.gjf) / 复旦 REST 输入</div>
                <div className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  自动附带净电荷、自旋多重度与标准基组模板
                </div>
              </div>
              <ArrowUpRight size={13.5} style={{ color: "var(--text-muted)" }} />
            </button>
          </div>

          <div className="pt-2 border-t space-y-1" style={{ borderColor: "var(--border-subtle)" }}>
            <div className="text-[11px] font-semibold" style={{ color: "var(--text-muted)" }}>
              最近分析记录
            </div>
            {recentAnalyses.length === 0 ? (
              <div className="text-[11.5px]" style={{ color: "var(--text-muted)" }}>
                尚无本次会话运行记录
              </div>
            ) : (
              recentAnalyses.slice(0, 3).map((rec, i) => (
                <div key={i} className="flex items-center justify-between text-[11.5px]">
                  <span className="truncate">
                    <span className="mono-num font-semibold" style={{ color: "var(--accent-primary)" }}>
                      {rec.analysisId}
                    </span>{" "}
                    {rec.title}
                  </span>
                  <span className="mono-num text-[10.5px]" style={{ color: "var(--text-muted)" }}>
                    {rec.timestamp}
                  </span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
