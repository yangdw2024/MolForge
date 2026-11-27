import React, { useEffect, useState } from "react";
import {
  Command,
  Minus,
  Moon,
  PanelRight,
  Redo2,
  Save,
  Square,
  Sun,
  Undo2,
  X,
} from "lucide-react";
import { molApi } from "../../services/api";
import { useStudioStore } from "../../store/useStudioStore";

export const MolForgeLogoMark: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <polygon
      points="12,2.5 20.2,7.25 20.2,16.75 12,21.5 3.8,16.75 3.8,7.25"
      stroke="var(--accent-primary)"
      strokeWidth="1.9"
      fill="var(--accent-soft)"
    />
    <polygon
      points="12,6.2 16.9,9.05 16.9,14.95 12,17.8 7.1,14.95 7.1,9.05"
      stroke="var(--accent-primary)"
      strokeWidth="1.2"
      strokeDasharray="2.5 2"
      opacity="0.8"
    />
    <circle cx="12" cy="12" r="2.2" fill="var(--accent-primary)" />
  </svg>
);

export const TitleBar: React.FC = () => {
  const summary = useStudioStore((s) => s.summary);
  const isDirty = useStudioStore((s) => s.isDirty);
  const projectPath = useStudioStore((s) => s.projectPath);
  const theme = useStudioStore((s) => s.theme);
  const inspectorOpen = useStudioStore((s) => s.inspectorOpen);
  const toggleTheme = useStudioStore((s) => s.toggleTheme);
  const setInspectorOpen = useStudioStore((s) => s.setInspectorOpen);
  const setCommandPaletteOpen = useStudioStore((s) => s.setCommandPaletteOpen);
  const saveProject = useStudioStore((s) => s.saveProject);
  const runTask = useStudioStore((s) => s.runTask);

  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    const api = window.molforgeDesktop;
    if (!api) return;
    void api.windowControls.isMaximized().then(setMaximized);
    return api.onEvent("window:maximized-changed", (val) => {
      setMaximized(Boolean(val));
    });
  }, []);

  const fileLabel = projectPath
    ? projectPath.split(/[\\/]/).pop()
    : summary?.name || "未命名工作区";

  return (
    <header
      data-testid="title-bar"
      className="app-drag h-[40px] shrink-0 px-3 flex items-center justify-between border-b"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-subtle)",
      }}
    >
      {/* Left: Brand & Project State */}
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="flex items-center gap-2 shrink-0">
          <MolForgeLogoMark size={19} />
          <span className="font-semibold text-[13px] tracking-tight" style={{ color: "var(--text-primary)" }}>
            MolForge Studio
          </span>
        </div>

        <span style={{ color: "var(--border-strong)" }}>/</span>

        <div className="app-no-drag flex items-center gap-1.5 min-w-0 px-2 py-0.5 rounded-md" style={{ backgroundColor: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}>
          <span
            className="text-[12px] font-medium truncate max-w-[200px]"
            title={projectPath || fileLabel}
            style={{ color: "var(--text-primary)" }}
          >
            {fileLabel}
          </span>
          {summary?.formula && (
            <span className="mono-num text-[11px] px-1.5 rounded" style={{ backgroundColor: "var(--accent-soft)", color: "var(--accent-primary)" }}>
              {summary.formula}
            </span>
          )}
          <span
            className="text-[11px] flex items-center gap-1 shrink-0"
            style={{ color: isDirty ? "var(--semantic-warning)" : "var(--text-muted)" }}
            title={isDirty ? "有未保存修改 (Ctrl+S 保存 .mforge)" : "工作区已同步"}
          >
            <span
              className="w-1.5 h-1.5 rounded-full inline-block"
              style={{ backgroundColor: isDirty ? "var(--semantic-warning)" : "var(--accent-primary)" }}
            />
            {isDirty ? "未保存" : "已同步"}
          </span>
        </div>

        <div className="app-no-drag flex items-center gap-1 ml-1">
          <button
            type="button"
            className="studio-btn !h-7 !px-2"
            disabled={!summary?.can_undo}
            onClick={() => void runTask("撤销", () => molApi.undo())}
            title="撤销上一步操作 (Ctrl+Z)"
          >
            <Undo2 size={13.5} />
          </button>
          <button
            type="button"
            className="studio-btn !h-7 !px-2"
            disabled={!summary?.can_redo}
            onClick={() => void runTask("重做", () => molApi.redo())}
            title="重做操作 (Ctrl+Y)"
          >
            <Redo2 size={13.5} />
          </button>
          <button
            type="button"
            className="studio-btn !h-7 !px-2"
            onClick={() => void saveProject(false)}
            title="保存 .mforge 工程 (Ctrl+S)"
          >
            <Save size={13.5} />
            <span className="hidden xl:inline">保存</span>
          </button>
        </div>
      </div>

      {/* Center: Global Command Palette Trigger */}
      <div className="app-no-drag flex-1 max-w-[340px] mx-4 hidden md:flex">
        <button
          type="button"
          data-testid="command-palette-trigger"
          onClick={() => setCommandPaletteOpen(true)}
          className="w-full h-7 px-2.5 rounded-md flex items-center justify-between text-[12px] cursor-pointer transition-colors"
          style={{
            backgroundColor: "var(--bg-input)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-secondary)",
          }}
        >
          <span className="flex items-center gap-1.5 truncate">
            <Command size={12.5} style={{ color: "var(--accent-primary)" }} />
            <span className="truncate">检索分子、分析模块、命令或快捷键...</span>
          </span>
          <kbd className="mono-num text-[10px] px-1.5 py-0.2 rounded" style={{ backgroundColor: "var(--bg-panel)", border: "1px solid var(--border-subtle)", color: "var(--text-muted)" }}>
            Ctrl+K
          </kbd>
        </button>
      </div>

      {/* Right: Theme, Inspector & Native Window Controls */}
      <div className="app-no-drag flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          data-testid="theme-toggle-btn"
          className="studio-btn !h-7 !px-2.5"
          onClick={toggleTheme}
          title={theme === "obsidian" ? "切换至 Arctic Laboratory (浅色)" : "切换至 Obsidian Laboratory (深色)"}
        >
          {theme === "obsidian" ? <Sun size={13.5} /> : <Moon size={13.5} />}
          <span className="hidden lg:inline text-[11.5px]">
            {theme === "obsidian" ? "Arctic 浅色" : "Obsidian 深色"}
          </span>
        </button>

        <button
          type="button"
          className="studio-btn !h-7 !px-2"
          onClick={() => setInspectorOpen(!inspectorOpen)}
          title="显隐右侧检查器"
          style={inspectorOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
        >
          <PanelRight size={13.5} />
        </button>

        {window.molforgeDesktop && (
          <div className="flex items-center ml-1 border-l pl-1.5 gap-0.5" style={{ borderColor: "var(--border-subtle)" }}>
            <button
              type="button"
              aria-label="最小化窗口"
              onClick={() => void window.molforgeDesktop?.windowControls.minimize()}
              className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-black/10 dark:hover:bg-white/10 transition-colors cursor-pointer"
              style={{ color: "var(--text-secondary)" }}
            >
              <Minus size={14} />
            </button>
            <button
              type="button"
              aria-label={maximized ? "还原窗口" : "最大化窗口"}
              onClick={() => void window.molforgeDesktop?.windowControls.toggleMaximize()}
              className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-black/10 dark:hover:bg-white/10 transition-colors cursor-pointer"
              style={{ color: "var(--text-secondary)" }}
            >
              <Square size={11.5} />
            </button>
            <button
              type="button"
              aria-label="关闭窗口"
              onClick={() => void window.molforgeDesktop?.windowControls.close()}
              className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-[#E5484D] hover:text-white transition-colors cursor-pointer"
              style={{ color: "var(--text-secondary)" }}
            >
              <X size={14} />
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
