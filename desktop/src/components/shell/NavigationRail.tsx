import React from "react";
import {
  Activity,
  Atom,
  Boxes,
  ChevronLeft,
  ChevronRight,
  Database,
  FileOutput,
  FlaskConical,
  LayoutDashboard,
  Settings,
} from "lucide-react";
import { useStudioStore } from "../../store/useStudioStore";
import type { NavRoute } from "../../types/studio";

const NAV_ITEMS: Array<{
  route: NavRoute;
  label: string;
  hint: string;
  icon: React.FC<{ size?: number }>;
}> = [
  { route: "overview", label: "工作台首页", hint: "项目概览与快速启动", icon: LayoutDashboard },
  { route: "library", label: "分子库", hint: "预设体系与结构数据库", icon: Database },
  { route: "editor", label: "分子编辑器", hint: "2D 绘图与 WebGPU 3D", icon: Atom },
  { route: "analysis", label: "分析中心", hint: "紧束缚能级与 79 项分析", icon: FlaskConical },
  { route: "hub", label: "MolForge Hub", hint: "插件、技能、工作流与 AI 编排", icon: Boxes },
  { route: "jobs", label: "任务中心", hint: "实时计算队列与日志", icon: Activity },
  { route: "reports", label: "结果与导出", hint: ".mforge 与量化输入归档", icon: FileOutput },
  { route: "settings", label: "偏好设置", hint: "主题、引擎与快捷键", icon: Settings },
];

export const NavigationRail: React.FC = () => {
  const activeRoute = useStudioStore((s) => s.activeRoute);
  const navExpanded = useStudioStore((s) => s.navExpanded);
  const showNavRail = useStudioStore((s) => s.showNavRail);
  const setRoute = useStudioStore((s) => s.setRoute);
  const setNavExpanded = useStudioStore((s) => s.setNavExpanded);
  const setShowNavRail = useStudioStore((s) => s.setShowNavRail);
  const jobs = useStudioStore((s) => s.jobs);

  const runningCount = jobs.filter((j) => j.status === "running" || j.status === "pending").length;

  if (!showNavRail) {
    return (
      <button
        type="button"
        onClick={() => setShowNavRail(true)}
        className="absolute bottom-9 left-2 z-30 p-1.5 rounded-lg border backdrop-blur-xl shadow-lg hover:scale-105 transition-all cursor-pointer"
        style={{
          backgroundColor: "color-mix(in srgb, var(--bg-secondary) 85%, transparent)",
          borderColor: "var(--border-subtle)",
          color: "var(--text-secondary)",
        }}
        title="展开侧边导航栏 (Ctrl+B)"
      >
        <ChevronRight size={15} />
      </button>
    );
  }

  return (
    <aside
      data-testid="nav-rail"
      className="shrink-0 border-r flex flex-col justify-between py-2.5 transition-[width] duration-200"
      style={{
        width: navExpanded ? 192 : 56,
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-subtle)",
      }}
    >
      <nav className="flex flex-col gap-1 px-2" aria-label="主功能导航">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = activeRoute === item.route;
          return (
            <button
              key={item.route}
              type="button"
              data-testid={`nav-${item.route}`}
              onClick={() => setRoute(item.route)}
              title={!navExpanded ? `${item.label} — ${item.hint}` : item.hint}
              className="relative h-9 px-2.5 rounded-lg flex items-center gap-2.5 text-left transition-colors cursor-pointer"
              style={{
                backgroundColor: active ? "var(--accent-soft)" : "transparent",
                color: active ? "var(--accent-primary)" : "var(--text-secondary)",
                fontWeight: active ? 600 : 500,
              }}
            >
              {active && (
                <span
                  className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full"
                  style={{ backgroundColor: "var(--accent-primary)" }}
                />
              )}
              <Icon size={16} />
              {navExpanded && <span className="text-[12.5px] truncate flex-1">{item.label}</span>}
              {item.route === "jobs" && runningCount > 0 && (
                <span
                  className="mono-num text-[10px] px-1.5 rounded-full font-semibold"
                  style={{ backgroundColor: "var(--accent-primary)", color: "var(--accent-contrast)" }}
                >
                  {runningCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="px-2 pt-2 border-t flex items-center gap-1" style={{ borderColor: "var(--border-subtle)" }}>
        <button
          type="button"
          onClick={() => setNavExpanded(!navExpanded)}
          className="flex-1 h-8 px-2 rounded-lg flex items-center justify-center gap-2 text-[11.5px] hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
          style={{ color: "var(--text-muted)" }}
          title={navExpanded ? "收起导航栏文字" : "展开导航栏文字"}
        >
          {navExpanded ? (
            <>
              <ChevronLeft size={14} />
              <span>收起导航文字</span>
            </>
          ) : (
            <ChevronRight size={14} />
          )}
        </button>
        <button
          type="button"
          onClick={() => setShowNavRail(false)}
          className="h-8 px-2 rounded-lg flex items-center justify-center hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
          style={{ color: "var(--text-muted)" }}
          title="完全隐藏侧边导航栏 (Ctrl+B)"
        >
          <ChevronLeft size={14} />
        </button>
      </div>
    </aside>
  );
};
