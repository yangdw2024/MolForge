import { useEffect } from "react";
import { molApi } from "./services/api";
import { useStudioStore } from "./store/useStudioStore";
import { StudioHeader } from "./components/shell/StudioHeader";
import { NavigationRail } from "./components/shell/NavigationRail";
import { InspectorPanel } from "./components/shell/InspectorPanel";
import { StatusBar } from "./components/shell/StatusBar";
import { CommandPalette } from "./components/shell/CommandPalette";
import { NotificationsDrawer } from "./components/shell/NotificationsDrawer";
import { OverviewView } from "./views/OverviewView";
import { LibraryView } from "./views/LibraryView";
import { EditorView } from "./views/EditorView";
import { AnalysisView } from "./views/AnalysisView";
import { HubView } from "./views/HubView";
import { JobsView } from "./views/JobsView";
import { ReportsView } from "./views/ReportsView";
import { SettingsView } from "./views/SettingsView";

export function App() {
  const activeRoute = useStudioStore((s) => s.activeRoute);
  const initWorkspace = useStudioStore((s) => s.initWorkspace);
  const refreshTelemetry = useStudioStore((s) => s.refreshTelemetry);
  const runAutosaveSnapshot = useStudioStore((s) => s.runAutosaveSnapshot);
  const setCommandPaletteOpen = useStudioStore((s) => s.setCommandPaletteOpen);
  const saveProject = useStudioStore((s) => s.saveProject);
  const openStructureDialog = useStudioStore((s) => s.openStructureDialog);
  const runTask = useStudioStore((s) => s.runTask);
  const setActiveTool = useStudioStore((s) => s.setActiveTool);
  const activeTool = useStudioStore((s) => s.activeTool);
  const triggerFitCamera = useStudioStore((s) => s.triggerFitCamera);
  const showHydrogens = useStudioStore((s) => s.showHydrogens);
  const setShowHydrogens = useStudioStore((s) => s.setShowHydrogens);
  const showNavRail = useStudioStore((s) => s.showNavRail);
  const setShowNavRail = useStudioStore((s) => s.setShowNavRail);
  const syncExternalChanges = useStudioStore((s) => s.syncExternalChanges);

  useEffect(() => {
    void initWorkspace();
    const teleTimer = setInterval(() => void refreshTelemetry(), 10000);
    const autoTimer = setInterval(() => void runAutosaveSnapshot(), 45000);
    // 500ms 轮询文档 revision：外部 API/其他客户端改文档后 UI 自动同步（只在 revision 变化时真刷新）
    const syncTimer = setInterval(() => void syncExternalChanges(), 500);
    return () => {
      clearInterval(teleTimer);
      clearInterval(autoTimer);
      clearInterval(syncTimer);
    };
  }, [initWorkspace, refreshTelemetry, runAutosaveSnapshot, syncExternalChanges]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const inInput =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandPaletteOpen(true);
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void saveProject(e.shiftKey);
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "o") {
        e.preventDefault();
        void openStructureDialog();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setShowNavRail(!showNavRail);
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !inInput) {
        e.preventDefault();
        void runTask("撤销", () => (e.shiftKey ? molApi.redo() : molApi.undo()));
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y" && !inInput) {
        e.preventDefault();
        void runTask("重做", () => molApi.redo());
        return;
      }
      if (inInput || e.ctrlKey || e.metaKey || e.altKey) return;

      const k = e.key.toLowerCase();
      // Shift+F 重置视角（菜单标注的真实快捷键）；裸 F 保留为片段工具
      if (k === "f" && e.shiftKey) {
        e.preventDefault();
        triggerFitCamera();
        return;
      }
      // H 切换显式氢（原子工具下悬停换元素优先，避免双重映射）
      if (k === "h" && activeTool !== "atom") {
        e.preventDefault();
        setShowHydrogens(!showHydrogens);
        return;
      }
      if (k === "v") setActiveTool("select");
      else if (k === "a") setActiveTool("atom");
      else if (k === "b") setActiveTool("bond");
      else if (k === "r") setActiveTool("ring");
      else if (k === "f") setActiveTool("fragment");
      else if (k === "e") setActiveTool("erase");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setCommandPaletteOpen, saveProject, openStructureDialog, runTask, setActiveTool, activeTool, triggerFitCamera, showHydrogens, setShowHydrogens, showNavRail, setShowNavRail]);

  return (
    <div
      className="h-screen w-screen flex flex-col overflow-hidden"
      style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
    >
      <StudioHeader />

      <div className="relative flex-1 flex min-h-0 overflow-hidden">
        <NavigationRail />

        <main className="flex-1 min-w-0 min-h-0 overflow-hidden">
          {activeRoute === "overview" && <OverviewView />}
          {activeRoute === "library" && <LibraryView />}
          {activeRoute === "editor" && <EditorView />}
          {activeRoute === "analysis" && <AnalysisView />}
          {activeRoute === "hub" && <HubView />}
          {activeRoute === "jobs" && <JobsView />}
          {activeRoute === "reports" && <ReportsView />}
          {activeRoute === "settings" && <SettingsView />}
        </main>

        <InspectorPanel />
      </div>

      <StatusBar />
      <CommandPalette />
      <NotificationsDrawer />
    </div>
  );
}

export default App;
