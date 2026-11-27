import React, { useEffect, useState } from "react";
import {
  Ban,
  CheckCircle2,
  Clock,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { useStudioStore } from "../store/useStudioStore";
import type { JobStatus } from "../types/studio";

const STATUS_STYLE: Record<JobStatus, { label: string; color: string; bg: string }> = {
  pending: { label: "Pending", color: "var(--text-secondary)", bg: "var(--bg-secondary)" },
  running: { label: "Running", color: "var(--semantic-info)", bg: "var(--semantic-info-soft)" },
  completed: { label: "Completed", color: "var(--accent-primary)", bg: "var(--accent-soft)" },
  failed: { label: "Failed", color: "var(--semantic-error)", bg: "var(--semantic-error-soft)" },
  cancelled: { label: "Cancelled", color: "var(--semantic-warning)", bg: "var(--semantic-warning-soft)" },
};

export const JobsView: React.FC = () => {
  const jobs = useStudioStore((s) => s.jobs);
  const summary = useStudioStore((s) => s.summary);
  const refreshJobs = useStudioStore((s) => s.refreshJobs);
  const submitBackgroundJob = useStudioStore((s) => s.submitBackgroundJob);
  const cancelBackgroundJob = useStudioStore((s) => s.cancelBackgroundJob);

  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const hasActive = jobs.some((j) => j.status === "pending" || j.status === "running");

  useEffect(() => {
    void refreshJobs();
    const timer = setInterval(() => {
      void refreshJobs();
    }, hasActive ? 450 : 2500);
    return () => clearInterval(timer);
  }, [hasActive, refreshJobs]);

  const activeJob = jobs.find((j) => j.job_id === selectedJobId) ?? jobs[0] ?? null;

  return (
    <div data-testid="view-jobs" className="h-full flex flex-col min-h-0 p-4 gap-3">
      {/* Quick Workflows Launcher */}
      <div className="studio-surface p-3 flex flex-wrap items-center justify-between gap-2 shrink-0">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            data-testid="submit-tb-job-btn"
            onClick={() =>
              void submitBackgroundJob("tight_binding", `Tight-Binding · ${summary?.name || "当前分子"}`)
            }
            className="studio-btn studio-btn-primary"
          >
            <Play size={13} />
            <span>提交 Tight-Binding 计算任务</span>
          </button>

          <button
            type="button"
            onClick={() =>
              void submitBackgroundJob("clean_3d", `3D 力场几何优化 · ${summary?.name || "当前分子"}`)
            }
            className="studio-btn"
          >
            <Play size={13} />
            <span>提交 3D 构象优化任务</span>
          </button>

          <button
            type="button"
            onClick={() =>
              void submitBackgroundJob("analysis", "CORE-01 摘要分析", { analysis_id: "CORE-01" })
            }
            className="studio-btn"
          >
            <Play size={13} />
            <span>提交 CORE-01 后台分析</span>
          </button>
        </div>

        <button type="button" onClick={() => void refreshJobs()} className="studio-btn">
          <RefreshCw size={12.5} />
          <span>刷新状态</span>
        </button>
      </div>

      {/* Main Split: Jobs List | Job Log & Result */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-3">
        <div className="lg:col-span-7 studio-surface flex flex-col overflow-hidden">
          <div className="px-3 py-2 border-b text-[12px] font-semibold flex items-center justify-between" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-secondary)" }}>
            <span>计算任务队列 ({jobs.length})</span>
            <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>真实绑定 Python 后台 Worker，不使用虚假进度条</span>
          </div>

          <div className="flex-1 studio-scroll">
            {jobs.length === 0 ? (
              <div className="p-8 text-center text-[12px]" style={{ color: "var(--text-muted)" }}>
                暂无后台任务。点击上方按钮提交真实计算任务。
              </div>
            ) : (
              <table className="w-full text-left border-collapse text-[12px]">
                <thead className="sticky top-0" style={{ backgroundColor: "var(--bg-secondary)", borderBottom: "1px solid var(--border-subtle)" }}>
                  <tr style={{ color: "var(--text-secondary)" }}>
                    <th className="p-2.5">任务名称</th>
                    <th className="p-2.5">状态</th>
                    <th className="p-2.5">耗时</th>
                    <th className="p-2.5 text-right">控制</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => {
                    const st = STATUS_STYLE[job.status];
                    const selected = job.job_id === activeJob?.job_id;
                    const duration =
                      job.finished_at && job.started_at
                        ? `${((job.finished_at - job.started_at) * 1000).toFixed(0)} ms`
                        : job.status === "running"
                        ? "执行中..."
                        : "—";
                    return (
                      <tr
                        key={job.job_id}
                        onClick={() => setSelectedJobId(job.job_id)}
                        className="border-b cursor-pointer transition-colors"
                        style={{
                          borderColor: "var(--border-subtle)",
                          backgroundColor: selected ? "var(--accent-soft)" : undefined,
                        }}
                      >
                        <td className="p-2.5">
                          <div className="font-medium">{job.name}</div>
                          <div className="mono-num text-[10.5px]" style={{ color: "var(--text-muted)" }}>
                            {job.job_id} · r{job.input_revision}
                          </div>
                        </td>
                        <td className="p-2.5">
                          <span
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium"
                            style={{ backgroundColor: st.bg, color: st.color }}
                          >
                            {job.status === "running" && <Loader2 size={11} className="animate-spin" />}
                            {job.status === "completed" && <CheckCircle2 size={11} />}
                            {job.status === "failed" && <XCircle size={11} />}
                            {job.status === "pending" && <Clock size={11} />}
                            {job.status === "cancelled" && <Ban size={11} />}
                            <span>{st.label}</span>
                          </span>
                        </td>
                        <td className="p-2.5 mono-num text-[11.5px]">{duration}</td>
                        <td className="p-2.5 text-right">
                          {job.status === "pending" || job.status === "running" ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                void cancelBackgroundJob(job.job_id);
                              }}
                              className="studio-btn !h-6 !px-2"
                            >
                              取消
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                void submitBackgroundJob(job.kind, job.name, job.params);
                              }}
                              className="studio-btn !h-6 !px-2"
                              title="使用相同参数重新运行"
                            >
                              <RotateCcw size={11} />
                              <span>重跑</span>
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Right: Logs & Output */}
        <div className="lg:col-span-5 studio-surface flex flex-col overflow-hidden">
          <div className="px-3 py-2 border-b text-[12px] font-semibold" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-secondary)" }}>
            任务日志与真实输出详情
          </div>

          {!activeJob ? (
            <div className="p-6 text-[12px]" style={{ color: "var(--text-muted)" }}>
              点击左侧任意任务查看启动时间、运行日志和计算结果。
            </div>
          ) : (
            <div className="flex-1 studio-scroll p-3 space-y-3 text-[12px]">
              <div className="studio-inset p-2.5 space-y-1">
                <div className="font-semibold">{activeJob.name}</div>
                <div className="mono-num text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  开始：{activeJob.started_at ? new Date(activeJob.started_at * 1000).toLocaleTimeString("zh-CN") : "—"} ·
                  结束：{activeJob.finished_at ? new Date(activeJob.finished_at * 1000).toLocaleTimeString("zh-CN") : "—"}
                </div>
                {activeJob.error && (
                  <div className="text-[11.5px] mt-1" style={{ color: "var(--semantic-error)" }}>
                    失败原因：{activeJob.error}
                  </div>
                )}
              </div>

              <div>
                <div className="text-[11px] font-semibold mb-1" style={{ color: "var(--text-muted)" }}>执行日志</div>
                <pre
                  className="p-2.5 rounded-lg mono-num text-[11px] whitespace-pre-wrap"
                  style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)", userSelect: "text" }}
                >
                  {activeJob.logs.join("\n")}
                </pre>
              </div>

              {activeJob.result != null && (
                <div>
                  <div className="text-[11px] font-semibold mb-1" style={{ color: "var(--text-muted)" }}>返回结果 (JSON)</div>
                  <pre
                    className="p-2.5 rounded-lg mono-num text-[11px] max-h-[240px] studio-scroll"
                    style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)", userSelect: "text" }}
                  >
                    {JSON.stringify(activeJob.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
