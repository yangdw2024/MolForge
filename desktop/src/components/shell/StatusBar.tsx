import React from "react";
import { AlertCircle, Bell, CheckCircle2, Cpu, Loader2, RefreshCw, X } from "lucide-react";
import { useStudioStore } from "../../store/useStudioStore";

export const StatusBar: React.FC = () => {
  const summary = useStudioStore((s) => s.summary);
  const busyLabel = useStudioStore((s) => s.busyLabel);
  const bridgeConnected = useStudioStore((s) => s.bridgeConnected);
  const telemetry = useStudioStore((s) => s.telemetry);
  const jobs = useStudioStore((s) => s.jobs);
  const notifications = useStudioStore((s) => s.notifications);
  const notificationsOpen = useStudioStore((s) => s.notificationsOpen);
  const setNotificationsOpen = useStudioStore((s) => s.setNotificationsOpen);
  const setRoute = useStudioStore((s) => s.setRoute);
  const refreshScene = useStudioStore((s) => s.refreshScene);
  const toasts = useStudioStore((s) => s.toasts);
  const dismissToast = useStudioStore((s) => s.dismissToast);

  const runningJobs = jobs.filter((j) => j.status === "running" || j.status === "pending").length;
  const errorCount = notifications.filter((n) => n.level === "error").length;

  return (
    <footer
      data-testid="status-bar"
      className="h-[26px] shrink-0 px-3 border-t flex items-center justify-between text-[11px]"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-subtle)",
        color: "var(--text-secondary)",
      }}
    >
      {/* 即时 toast 堆栈：任务失败/成功当场可见 */}
      <div data-testid="toast-stack" className="fixed right-3 bottom-9 z-[9000] flex flex-col gap-2 w-[340px] pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            data-testid="toast"
            className="pointer-events-auto rounded-lg border shadow-lg px-3 py-2 flex items-start gap-2 text-[11.5px] leading-snug"
            style={{
              backgroundColor: "var(--bg-panel)",
              borderColor: t.level === "error" ? "var(--semantic-error)" : t.level === "warning" ? "#F59E0B" : "var(--accent-primary)",
              color: "var(--text-primary)",
            }}
          >
            {t.level === "error" ? (
              <AlertCircle size={14} style={{ color: "var(--semantic-error)", flexShrink: 0, marginTop: 1 }} />
            ) : (
              <CheckCircle2 size={14} style={{ color: t.level === "warning" ? "#F59E0B" : "var(--accent-primary)", flexShrink: 0, marginTop: 1 }} />
            )}
            <div className="min-w-0 flex-1">
              <div className="font-semibold">{t.title}</div>
              {t.detail && <div className="opacity-75 break-all mt-0.5 max-h-16 overflow-auto">{t.detail}</div>}
            </div>
            <button type="button" onClick={() => dismissToast(t.id)} className="opacity-60 hover:opacity-100 cursor-pointer" title="关闭">
              <X size={12} />
            </button>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={async () => {
            if (!bridgeConnected && window.molforgeDesktop) {
              await window.molforgeDesktop.system.restartBridge();
            }
            await refreshScene();
          }}
          className="flex items-center gap-1.5 cursor-pointer hover:underline"
          title="点击检测或重连 Python 化学引擎"
        >
          <span
            className="w-2 h-2 rounded-full inline-block"
            style={{
              backgroundColor: bridgeConnected
                ? "var(--accent-primary)"
                : "var(--semantic-error)",
            }}
          />
          <span>{bridgeConnected ? "化学计算内核在线 (:18765)" : "引擎未连接 · 点击重连"}</span>
          {!bridgeConnected && <RefreshCw size={10.5} />}
        </button>

        {summary && (
          <span className="mono-num truncate hidden sm:inline" style={{ color: "var(--text-muted)" }}>
            {summary.name} · {summary.num_atoms.toLocaleString()} 原子 / {summary.num_bonds.toLocaleString()} 键 · r{summary.revision}
          </span>
        )}

        {busyLabel && (
          <span className="flex items-center gap-1" style={{ color: "var(--semantic-info)" }}>
            <Loader2 size={11} className="animate-spin" />
            <span>{busyLabel}</span>
          </span>
        )}
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <button
          type="button"
          onClick={() => setRoute("jobs")}
          className="flex items-center gap-1 cursor-pointer hover:underline"
        >
          <Cpu size={11} />
          <span className="mono-num">
            {runningJobs > 0 ? `${runningJobs} 个计算运行中` : "计算队列空闲"}
          </span>
        </button>

        {telemetry && (
          <span className="mono-num hidden md:inline" style={{ color: "var(--text-muted)" }}>
            RSS {telemetry.rssMb} MB · 可用内存 {telemetry.sysFreeGb}/{telemetry.sysTotalGb} GB
          </span>
        )}

        <button
          type="button"
          onClick={() => setNotificationsOpen(!notificationsOpen)}
          className="flex items-center gap-1 cursor-pointer px-1.5 py-0.5 rounded hover:bg-black/5 dark:hover:bg-white/5"
          style={{ color: errorCount > 0 ? "var(--semantic-error)" : "var(--text-secondary)" }}
          title="查看事件与通知日志"
        >
          {errorCount > 0 ? <AlertCircle size={11.5} /> : <Bell size={11.5} />}
          <span className="mono-num">{notifications.length}</span>
        </button>

        <span className="mono-num hidden lg:inline" style={{ color: "var(--text-muted)" }}>
          v8.1.0
        </span>
      </div>
    </footer>
  );
};
