import React from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useStudioStore } from "../../store/useStudioStore";

export const NotificationsDrawer: React.FC = () => {
  const open = useStudioStore((s) => s.notificationsOpen);
  const setOpen = useStudioStore((s) => s.setNotificationsOpen);
  const notifications = useStudioStore((s) => s.notifications);

  if (!open) return null;

  return (
    <div
      className="fixed bottom-8 right-3 z-40 w-[360px] max-h-[420px] studio-surface flex flex-col overflow-hidden"
      style={{ boxShadow: "var(--shadow-modal)" }}
    >
      <div className="px-3 py-2 border-b flex items-center justify-between" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-secondary)" }}>
        <span className="text-[12px] font-semibold">系统事件与诊断通知 ({notifications.length})</span>
        <button type="button" onClick={() => setOpen(false)} className="p-1 rounded cursor-pointer" style={{ color: "var(--text-muted)" }}>
          <X size={13} />
        </button>
      </div>
      <div className="flex-1 studio-scroll p-2 space-y-1.5">
        {notifications.length === 0 ? (
          <div className="py-6 text-center text-[11.5px]" style={{ color: "var(--text-muted)" }}>
            暂无通知事件
          </div>
        ) : (
          notifications.map((n) => (
            <div key={n.id} className="studio-inset p-2 text-[11.5px] flex items-start gap-2">
              {n.level === "error" ? (
                <AlertCircle size={13.5} className="shrink-0 mt-0.5" style={{ color: "var(--semantic-error)" }} />
              ) : n.level === "success" ? (
                <CheckCircle2 size={13.5} className="shrink-0 mt-0.5" style={{ color: "var(--accent-primary)" }} />
              ) : (
                <Info size={13.5} className="shrink-0 mt-0.5" style={{ color: "var(--semantic-info)" }} />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium truncate">{n.title}</span>
                  <span className="mono-num text-[10px]" style={{ color: "var(--text-muted)" }}>{n.timestamp}</span>
                </div>
                {n.detail && (
                  <div className="text-[11px] break-all mt-0.5" style={{ color: "var(--text-secondary)" }}>
                    {n.detail}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
