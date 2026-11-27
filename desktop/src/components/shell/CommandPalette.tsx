import React, { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Command, Search, X } from "lucide-react";
import { molApi } from "../../services/api";
import { useStudioStore } from "../../store/useStudioStore";

interface PaletteAction {
  id: string;
  group: string;
  title: string;
  subtitle?: string;
  run: () => void;
}

export const CommandPalette: React.FC = () => {
  const open = useStudioStore((s) => s.commandPaletteOpen);
  const setOpen = useStudioStore((s) => s.setCommandPaletteOpen);
  const setRoute = useStudioStore((s) => s.setRoute);
  const toggleTheme = useStudioStore((s) => s.toggleTheme);
  const summary = useStudioStore((s) => s.summary);
  const analysisCatalog = useStudioStore((s) => s.analysisCatalog);
  const openStructureDialog = useStudioStore((s) => s.openStructureDialog);
  const saveProject = useStudioStore((s) => s.saveProject);
  const runTask = useStudioStore((s) => s.runTask);
  const runAndRecordAnalysis = useStudioStore((s) => s.runAndRecordAnalysis);
  const setPeriodicModalOpen = useStudioStore((s) => s.setPeriodicModalOpen);

  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  const actions = useMemo<PaletteAction[]>(() => {
    const base: PaletteAction[] = [
      { id: "nav-overview", group: "页面导航", title: "打开工作台首页 (Overview)", run: () => setRoute("overview") },
      { id: "nav-library", group: "页面导航", title: "打开分子库 (Molecule Library)", run: () => setRoute("library") },
      { id: "nav-editor", group: "页面导航", title: "打开 2D/3D 分子编辑器", run: () => setRoute("editor") },
      { id: "nav-analysis", group: "页面导航", title: "打开计算与分析中心", run: () => setRoute("analysis") },
      { id: "nav-jobs", group: "页面导航", title: "打开后台任务中心", run: () => setRoute("jobs") },
      { id: "nav-reports", group: "页面导航", title: "打开结果与导出中心", run: () => setRoute("reports") },
      { id: "nav-settings", group: "页面导航", title: "打开偏好设置", run: () => setRoute("settings") },
      { id: "act-theme", group: "外观与操作", title: "切换深浅主题 (Obsidian / Arctic)", run: () => toggleTheme() },
      { id: "act-open", group: "文件与工程", title: "打开本地分子结构或 .mforge 工程...", run: () => void openStructureDialog() },
      { id: "act-save", group: "文件与工程", title: "保存当前 .mforge 工程 (Ctrl+S)", run: () => void saveProject(false) },
      { id: "act-clean", group: "分子编辑", title: "执行 3D 力场几何整理", run: () => void runTask("3D 几何优化", () => molApi.clean3D()) },
      { id: "act-pt", group: "分子编辑", title: "打开完整 118 元素周期表选择器", run: () => { setRoute("editor"); setPeriodicModalOpen(true); } },
    ];
    for (const p of summary?.presets ?? []) {
      base.push({
        id: `preset-${p.id}`,
        group: "加载预设体系",
        title: `加载 ${p.label}`,
        subtitle: p.smiles,
        run: () => void runTask(`加载 ${p.name}`, () => molApi.loadPreset(p.id), true),
      });
    }
    for (const a of analysisCatalog.slice(0, 24)) {
      base.push({
        id: `an-${a.id}`,
        group: "科研分析项",
        title: `${a.id} · ${a.title}`,
        subtitle: `${a.category} | ${a.engine}`,
        run: () => {
          setRoute("analysis");
          void runAndRecordAnalysis(a.id);
        },
      });
    }
    return base;
  }, [summary, analysisCatalog, setRoute, toggleTheme, openStructureDialog, saveProject, runTask, runAndRecordAnalysis, setPeriodicModalOpen]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions.slice(0, 14);
    return actions
      .filter(
        (a) =>
          a.title.toLowerCase().includes(q) ||
          a.group.toLowerCase().includes(q) ||
          (a.subtitle && a.subtitle.toLowerCase().includes(q))
      )
      .slice(0, 18);
  }, [actions, query]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4"
      style={{ backgroundColor: "rgba(5, 10, 18, 0.58)" }}
      onClick={() => setOpen(false)}
    >
      <div
        data-testid="command-palette"
        className="w-full max-w-[600px] studio-surface overflow-hidden"
        style={{ boxShadow: "var(--shadow-modal)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-3 py-2.5 border-b" style={{ borderColor: "var(--border-subtle)" }}>
          <Search size={15} style={{ color: "var(--accent-primary)" }} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
              if (e.key === "Enter" && filtered[0]) {
                filtered[0].run();
                setOpen(false);
              }
            }}
            placeholder="输入命令、分子预设、分析编号（如 WFN-01）..."
            className="flex-1 bg-transparent border-0 outline-none text-[13px]"
            style={{ color: "var(--text-primary)", userSelect: "text" }}
          />
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10 cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <X size={14} />
          </button>
        </div>

        <div className="max-h-[380px] studio-scroll p-1.5">
          {filtered.length === 0 ? (
            <div className="py-8 text-center text-[12px]" style={{ color: "var(--text-muted)" }}>
              未找到匹配命令或科研模块
            </div>
          ) : (
            filtered.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  item.run();
                  setOpen(false);
                }}
                className="w-full px-3 py-2 rounded-lg flex items-center justify-between gap-3 text-left hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer transition-colors"
              >
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium truncate" style={{ color: "var(--text-primary)" }}>
                    {item.title}
                  </div>
                  {item.subtitle && (
                    <div className="mono-num text-[11px] truncate" style={{ color: "var(--text-muted)" }}>
                      {item.subtitle}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10.5px] px-1.5 py-0.5 rounded" style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-secondary)" }}>
                    {item.group}
                  </span>
                  <ArrowRight size={12.5} style={{ color: "var(--text-muted)" }} />
                </div>
              </button>
            ))
          )}
        </div>

        <div className="px-3 py-1.5 border-t flex items-center justify-between text-[11px]" style={{ borderColor: "var(--border-subtle)", color: "var(--text-muted)", backgroundColor: "var(--bg-secondary)" }}>
          <span className="flex items-center gap-1"><Command size={11} /> Enter 执行首项</span>
          <span>Esc 关闭</span>
        </div>
      </div>
    </div>
  );
};
