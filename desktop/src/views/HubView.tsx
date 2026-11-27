import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  Cpu,
  FileCode2,
  GitBranch,
  Pin,
  Play,
  Plus,
  Search,
  ShieldAlert,
  Sparkles,
  Star,
  Workflow,
  XCircle,
} from "lucide-react";
import { molApi } from "../services/api";
import { useStudioStore } from "../store/useStudioStore";
import type {
  HubResource,
  HubResourceKind,
  WorkflowProposal,
  WorkflowRun,
  WorkflowSpec,
} from "../types/studio";

type HubFilter = "all" | HubResourceKind | "favorites";

const KIND_LABELS: Record<HubResourceKind, string> = {
  plugin: "软件与插件",
  skill: "AI 技能",
  workflow: "科研工作流",
  model: "模型与资产",
};

const SAMPLE_SKILL_MD = `---
name: custom-homo-lumo-check
description: Verify charge, spin multiplicity, and HOMO-LUMO gap consistency before exporting QC inputs.
---
# Custom Frontier Orbital Check
1. Confirm molecule charge and multiplicity.
2. Run \`qc.tight_binding\` for rapid pi-gap inspection.
3. Cross-check with \`qc.calchem_scf\` when ab initio accuracy is required.
`;

export const HubView: React.FC = () => {
  const pushNotification = useStudioStore((s) => s.pushNotification);
  const currentDoc = useStudioStore((s) => s.summary);

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<HubFilter>("all");
  const [resources, setResources] = useState<HubResource[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowSpec[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(false);

  const [aiPrompt, setAiPrompt] = useState("分析当前分子的前线轨道 HOMO/LUMO 与能隙");
  const [proposal, setProposal] = useState<WorkflowProposal | null>(null);
  const [activeRun, setActiveRun] = useState<WorkflowRun | null>(null);

  const [showSkillModal, setShowSkillModal] = useState(false);
  const [skillMarkdown, setSkillMarkdown] = useState(SAMPLE_SKILL_MD);

  const refreshHub = useCallback(async () => {
    setLoading(true);
    try {
      const apiKind = filter === "favorites" ? "all" : filter;
      const [resList, wfCat, wfRuns] = await Promise.all([
        molApi.getHubResources(query.trim() || undefined, apiKind),
        molApi.getWorkflowsCatalog(),
        molApi.getWorkflowRuns(),
      ]);
      const filtered =
        filter === "favorites"
          ? resList.items.filter((i) => i.favorite || i.pinned)
          : resList.items;
      setResources(filtered);
      setWorkflows(wfCat.workflows);
      setRuns(wfRuns.runs);
    } catch (err) {
      pushNotification("error", "Hub 注册表加载失败", String(err));
    } finally {
      setLoading(false);
    }
  }, [query, filter, pushNotification]);

  useEffect(() => {
    void refreshHub();
  }, [refreshHub]);

  const handleToggleFavorite = async (id: string) => {
    try {
      await molApi.toggleHubFavorite(id);
      await refreshHub();
    } catch (err) {
      pushNotification("error", "收藏操作失败", String(err));
    }
  };

  const handleTogglePin = async (id: string) => {
    try {
      await molApi.toggleHubPin(id);
      await refreshHub();
    } catch (err) {
      pushNotification("error", "置顶操作失败", String(err));
    }
  };

  const handlePlanWorkflow = async (promptOverride?: string) => {
    const q = (promptOverride ?? aiPrompt).trim();
    if (!q) return;
    try {
      const res = await molApi.planWorkflow(q);
      setProposal(res.proposal);
    } catch (err) {
      pushNotification("error", "AI 工作流规划失败", String(err));
    }
  };

  const handleRunWorkflow = async (workflowId: string, approved = false) => {
    try {
      const res = await molApi.runWorkflow(workflowId, approved);
      setActiveRun(res.run);
      await refreshHub();
      if (res.run.status === "completed") {
        pushNotification("success", "工作流执行完成", res.run.title);
      } else if (res.run.status === "pending_approval") {
        pushNotification("warning", "等待用户审批", "该工作流包含外部进程执行权限，请确认后批准运行");
      } else if (res.run.status === "blocked") {
        pushNotification("warning", "工作流因缺失依赖被阻断", res.run.error ?? "");
      }
    } catch (err) {
      pushNotification("error", "工作流执行失败", String(err));
    }
  };

  const handleImportSkill = async () => {
    try {
      const res = await molApi.importSkillMd(skillMarkdown, "local://user-import", []);
      const warnings = (res.skill.security_warnings as string[] | undefined) ?? [];
      if (warnings.length > 0) {
        pushNotification("warning", "技能已按低信任模式导入", warnings.join("；"));
      } else {
        pushNotification("success", "SKILL.md 导入成功", String(res.skill.name ?? ""));
      }
      setShowSkillModal(false);
      await refreshHub();
    } catch (err) {
      pushNotification("error", "SKILL.md 校验失败", String(err));
    }
  };

  return (
    <div data-testid="view-hub" className="h-full overflow-y-auto p-4 space-y-4">
      {/* Header + Unified Search */}
      <div
        className="rounded-xl border p-4 space-y-3"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-subtle)" }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Boxes size={18} style={{ color: "var(--accent-primary)" }} />
              <h1 className="text-[15px] font-semibold">MolForge Hub · 统一科研扩展与工作流中心</h1>
            </div>
            <p className="text-[12px] mt-0.5" style={{ color: "var(--text-secondary)" }}>
              插件提供工具 · Agent Skills 提供方法 · 工作流提供确定性步骤 · AI 负责意图理解与编排（当前分子：
              <span className="font-mono font-medium">{currentDoc?.name ?? "未加载"}</span>）
            </p>
          </div>
          <button
            type="button"
            data-testid="hub-import-skill-btn"
            onClick={() => setShowSkillModal(true)}
            className="h-8 px-3 rounded-lg border text-[12px] font-medium flex items-center gap-1.5 cursor-pointer"
            style={{
              backgroundColor: "var(--bg-tertiary)",
              borderColor: "var(--border-subtle)",
              color: "var(--text-primary)",
            }}
          >
            <Plus size={14} />
            导入 SKILL.md
          </button>
        </div>

        {/* Search + Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <div
            className="flex-1 min-w-[240px] h-9 px-3 rounded-lg border flex items-center gap-2"
            style={{ backgroundColor: "var(--bg-primary)", borderColor: "var(--border-subtle)" }}
          >
            <Search size={14} style={{ color: "var(--text-muted)" }} />
            <input
              data-testid="hub-search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索能力、插件、SKILL.md 或工作流（如：RDF、HOMO、CalChem、xTB、Multiwfn）..."
              className="w-full bg-transparent text-[12.5px] outline-none"
              style={{ color: "var(--text-primary)" }}
            />
          </div>

          <div className="flex items-center gap-1 flex-wrap">
            {(
              [
                ["all", "全部"],
                ["favorites", "收藏/置顶"],
                ["workflow", "科研工作流"],
                ["skill", "AI 技能"],
                ["plugin", "软件与插件"],
                ["model", "模型与资产"],
              ] as Array<[HubFilter, string]>
            ).map(([key, label]) => {
              const active = filter === key;
              return (
                <button
                  key={key}
                  type="button"
                  data-testid={`hub-filter-${key}`}
                  onClick={() => setFilter(key)}
                  className="h-8 px-2.5 rounded-lg text-[12px] border cursor-pointer transition-colors"
                  style={{
                    backgroundColor: active ? "var(--accent-soft)" : "var(--bg-primary)",
                    borderColor: active ? "var(--accent-primary)" : "var(--border-subtle)",
                    color: active ? "var(--accent-primary)" : "var(--text-secondary)",
                    fontWeight: active ? 600 : 500,
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* AI Intent -> Skill -> Workflow Planner */}
      <div
        className="rounded-xl border p-4 space-y-3"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-subtle)" }}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles size={15} style={{ color: "var(--accent-primary)" }} />
            <h2 className="text-[13px] font-semibold">AI 技能匹配与工作流草稿编排</h2>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {[
              "前线轨道 HOMO/LUMO 分析",
              "CalChem 从头算 SCF 计算",
              "GROMACS 轨迹 RDF 分析",
            ].map((sample) => (
              <button
                key={sample}
                type="button"
                onClick={() => {
                  setAiPrompt(sample);
                  void handlePlanWorkflow(sample);
                }}
                className="px-2 py-0.5 rounded border text-[11px] cursor-pointer"
                style={{
                  backgroundColor: "var(--bg-primary)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-secondary)",
                }}
              >
                {sample}
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <input
            data-testid="hub-ai-prompt-input"
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handlePlanWorkflow();
            }}
            placeholder="描述科研目标，例如：帮我分析当前分子的 HOMO/LUMO 能隙，或对轨迹做 RDF 分析..."
            className="flex-1 h-9 px-3 rounded-lg border text-[12.5px] outline-none"
            style={{
              backgroundColor: "var(--bg-primary)",
              borderColor: "var(--border-subtle)",
              color: "var(--text-primary)",
            }}
          />
          <button
            type="button"
            data-testid="hub-ai-plan-btn"
            onClick={() => void handlePlanWorkflow()}
            className="h-9 px-4 rounded-lg text-[12.5px] font-semibold cursor-pointer flex items-center gap-1.5"
            style={{
              backgroundColor: "var(--accent-primary)",
              color: "var(--accent-contrast)",
            }}
          >
            <Workflow size={14} />
            匹配技能并生成计划
          </button>
        </div>

        {proposal && (
          <div
            data-testid="hub-ai-proposal"
            className="rounded-lg border p-3 space-y-2.5"
            style={{ backgroundColor: "var(--bg-primary)", borderColor: "var(--border-subtle)" }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <GitBranch size={14} style={{ color: "var(--accent-primary)" }} />
                <span className="text-[13px] font-semibold">{proposal.selected_workflow.title}</span>
                <span
                  className="text-[11px] px-2 py-0.5 rounded-full font-medium"
                  style={{
                    backgroundColor: proposal.runnable
                      ? "rgba(16, 185, 129, 0.14)"
                      : "rgba(239, 68, 68, 0.14)",
                    color: proposal.runnable ? "#10b981" : "#ef4444",
                  }}
                >
                  {proposal.runnable ? "依赖就绪 · 可审核执行" : "缺失依赖 · 禁止执行"}
                </span>
              </div>
              <button
                type="button"
                data-testid="hub-run-proposal-btn"
                onClick={() => void handleRunWorkflow(proposal.selected_workflow.id, false)}
                className="h-7 px-3 rounded-md text-[12px] font-medium flex items-center gap-1.5 cursor-pointer"
                style={{
                  backgroundColor: "var(--accent-primary)",
                  color: "var(--accent-contrast)",
                }}
              >
                <Play size={12} />
                运行 / 审核工作流
              </button>
            </div>

            <p className="text-[12px]" style={{ color: "var(--text-secondary)" }}>
              {proposal.explanation}
            </p>

            {/* DAG Nodes */}
            <div className="flex items-center gap-2 flex-wrap">
              {proposal.selected_workflow.nodes.map((node, i) => (
                <React.Fragment key={node.id}>
                  <div
                    className="px-2.5 py-1.5 rounded-md border text-[11.5px]"
                    style={{
                      backgroundColor: "var(--bg-secondary)",
                      borderColor: "var(--border-subtle)",
                    }}
                  >
                    <div className="font-medium">{node.title}</div>
                    <div className="text-[10.5px] font-mono" style={{ color: "var(--text-muted)" }}>
                      {node.kind}
                      {node.capability ? ` · ${node.capability}` : ""}
                    </div>
                  </div>
                  {i < proposal.selected_workflow.nodes.length - 1 && (
                    <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>
                      →
                    </span>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Active Workflow Run & Provenance Panel */}
      {activeRun && (
        <div
          data-testid="hub-active-run"
          className="rounded-xl border p-4 space-y-3"
          style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-subtle)" }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {activeRun.status === "completed" ? (
                <CheckCircle2 size={16} style={{ color: "#10b981" }} />
              ) : activeRun.status === "pending_approval" ? (
                <ShieldAlert size={16} style={{ color: "#f59e0b" }} />
              ) : (
                <XCircle size={16} style={{ color: "#ef4444" }} />
              )}
              <span className="text-[13.5px] font-semibold">
                {activeRun.title} · <span className="font-mono text-[12px]">{activeRun.status}</span>
              </span>
            </div>

            {activeRun.status === "pending_approval" && (
              <button
                type="button"
                data-testid="hub-approve-run-btn"
                onClick={() => void handleRunWorkflow(activeRun.workflow_id, true)}
                className="h-8 px-3 rounded-lg text-[12px] font-semibold cursor-pointer"
                style={{ backgroundColor: "#f59e0b", color: "#0f172a" }}
              >
                批准外部进程权限并执行
              </button>
            )}
          </div>

          {activeRun.error && (
            <div
              className="rounded-lg border p-2.5 text-[12px]"
              style={{
                backgroundColor: "rgba(239, 68, 68, 0.08)",
                borderColor: "rgba(239, 68, 68, 0.35)",
                color: "#ef4444",
              }}
            >
              {activeRun.error}
            </div>
          )}

          {activeRun.node_records.length > 0 && (
            <div className="space-y-1.5">
              {activeRun.node_records.map((nr) => (
                <div
                  key={nr.node_id}
                  className="rounded-lg border px-3 py-2 flex items-center justify-between gap-3 text-[12px]"
                  style={{
                    backgroundColor: "var(--bg-primary)",
                    borderColor: "var(--border-subtle)",
                  }}
                >
                  <div>
                    <span className="font-semibold">{nr.title}</span>
                    <span className="ml-2" style={{ color: "var(--text-secondary)" }}>
                      {nr.summary}
                    </span>
                  </div>
                  <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
                    {nr.status} · {nr.duration_ms} ms
                  </span>
                </div>
              ))}
            </div>
          )}

          <div
            className="rounded-lg border p-2.5 text-[11px] font-mono space-y-0.5"
            style={{
              backgroundColor: "var(--bg-primary)",
              borderColor: "var(--border-subtle)",
              color: "var(--text-secondary)",
            }}
          >
            <div>
              Provenance Run: {activeRun.provenance.run_id} | Workflow: {activeRun.provenance.workflow_id}@
              {activeRun.provenance.workflow_version}
            </div>
            <div>
              Input Molecule: {activeRun.provenance.input_molecule_name} ({activeRun.provenance.input_molecule_formula}
              ) · SHA256: {activeRun.provenance.input_molecule_sha256.slice(0, 16)}...
            </div>
            <div>
              Skills: {activeRun.provenance.matched_skill_ids.join(", ") || "none"} | Approved:{" "}
              {String(activeRun.provenance.approved_by_user)}
            </div>
          </div>
        </div>
      )}

      {/* Unified Resource Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {resources.map((item) => {
          const wfSpec =
            item.kind === "workflow" ? workflows.find((w) => w.id === item.id) : undefined;
          return (
            <div
              key={item.id}
              data-testid={`hub-card-${item.id}`}
              className="rounded-xl border p-3.5 flex flex-col justify-between gap-2.5"
              style={{
                backgroundColor: "var(--bg-secondary)",
                borderColor: "var(--border-subtle)",
              }}
            >
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className="text-[10.5px] px-1.5 py-0.5 rounded font-medium"
                      style={{
                        backgroundColor: "var(--accent-soft)",
                        color: "var(--accent-primary)",
                      }}
                    >
                      {KIND_LABELS[item.kind]}
                    </span>
                    <span className="text-[10.5px] font-mono" style={{ color: "var(--text-muted)" }}>
                      v{item.version}
                    </span>
                    {!item.trusted && (
                      <span
                        className="text-[10.5px] px-1.5 py-0.5 rounded font-medium"
                        style={{ backgroundColor: "rgba(245, 158, 11, 0.16)", color: "#f59e0b" }}
                      >
                        低信任导入
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => void handleToggleFavorite(item.id)}
                      title="收藏"
                      className="p-1 rounded hover:opacity-80 cursor-pointer"
                      style={{ color: item.favorite ? "#f59e0b" : "var(--text-muted)" }}
                    >
                      <Star size={13} fill={item.favorite ? "currentColor" : "none"} />
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleTogglePin(item.id)}
                      title="固定到快捷栏"
                      className="p-1 rounded hover:opacity-80 cursor-pointer"
                      style={{ color: item.pinned ? "var(--accent-primary)" : "var(--text-muted)" }}
                    >
                      <Pin size={13} />
                    </button>
                  </div>
                </div>

                <div className="text-[13px] font-semibold flex items-center gap-1.5">
                  {item.kind === "plugin" && <Cpu size={13} />}
                  {item.kind === "skill" && <FileCode2 size={13} />}
                  {item.kind === "workflow" && <Workflow size={13} />}
                  <span className="truncate">{item.title}</span>
                </div>

                <p className="text-[12px] line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                  {item.description}
                </p>

                {item.security_warnings.length > 0 && (
                  <div
                    className="rounded border px-2 py-1 text-[11px] flex items-start gap-1.5"
                    style={{
                      backgroundColor: "rgba(245, 158, 11, 0.08)",
                      borderColor: "rgba(245, 158, 11, 0.35)",
                      color: "#f59e0b",
                    }}
                  >
                    <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                    <span>{item.security_warnings[0]}</span>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t flex items-center justify-between gap-2" style={{ borderColor: "var(--border-subtle)" }}>
                <span
                  className="text-[11px] truncate"
                  style={{ color: item.runnable ? "#10b981" : "var(--text-muted)" }}
                  title={item.status_reason}
                >
                  {item.status_reason}
                </span>

                {wfSpec && (
                  <button
                    type="button"
                    data-testid={`hub-run-wf-${item.id}`}
                    onClick={() => void handleRunWorkflow(item.id, false)}
                    className="h-7 px-2.5 rounded-md text-[11.5px] font-medium shrink-0 flex items-center gap-1 cursor-pointer"
                    style={{
                      backgroundColor: item.runnable ? "var(--accent-primary)" : "var(--bg-tertiary)",
                      color: item.runnable ? "var(--accent-contrast)" : "var(--text-secondary)",
                    }}
                  >
                    <Play size={11} />
                    执行
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {!loading && resources.length === 0 && (
        <div className="text-center py-8 text-[12.5px]" style={{ color: "var(--text-muted)" }}>
          未找到匹配的 Hub 资源，请调整搜索关键词或分类筛选。
        </div>
      )}

      {runs.length > 0 && (
        <div
          className="rounded-xl border p-3.5 space-y-2"
          style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-subtle)" }}
        >
          <div className="text-[12.5px] font-semibold">最近工作流溯源记录 ({runs.length})</div>
          <div className="space-y-1">
            {runs.slice(0, 5).map((r) => (
              <button
                key={r.run_id}
                type="button"
                onClick={() => setActiveRun(r)}
                className="w-full text-left rounded-lg border px-3 py-1.5 flex items-center justify-between text-[11.5px] cursor-pointer"
                style={{
                  backgroundColor: "var(--bg-primary)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <span>
                  <span className="font-mono">{r.run_id}</span> · {r.title}
                </span>
                <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                  {r.status}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Import SKILL.md Modal */}
      {showSkillModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div
            data-testid="hub-skill-import-modal"
            className="w-full max-w-2xl rounded-xl border p-4 space-y-3"
            style={{
              backgroundColor: "var(--bg-secondary)",
              borderColor: "var(--border-subtle)",
            }}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-[14px] font-semibold">导入本地 Agent Skill (`SKILL.md`)</h3>
              <button
                type="button"
                onClick={() => setShowSkillModal(false)}
                className="text-[12px] cursor-pointer"
                style={{ color: "var(--text-muted)" }}
              >
                关闭
              </button>
            </div>
            <p className="text-[11.5px]" style={{ color: "var(--text-secondary)" }}>
              仅解析标准 YAML frontmatter (`name`、`description`) 与只读科研指导正文；任何嵌入的 shell
              指令都不会被自动执行或赋予权限。
            </p>
            <textarea
              data-testid="hub-skill-textarea"
              value={skillMarkdown}
              onChange={(e) => setSkillMarkdown(e.target.value)}
              rows={11}
              className="w-full rounded-lg border p-2.5 font-mono text-[12px] outline-none"
              style={{
                backgroundColor: "var(--bg-primary)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowSkillModal(false)}
                className="h-8 px-3 rounded-lg border text-[12px] cursor-pointer"
                style={{ borderColor: "var(--border-subtle)" }}
              >
                取消
              </button>
              <button
                type="button"
                data-testid="hub-skill-confirm-btn"
                onClick={() => void handleImportSkill()}
                className="h-8 px-4 rounded-lg text-[12px] font-semibold cursor-pointer"
                style={{
                  backgroundColor: "var(--accent-primary)",
                  color: "var(--accent-contrast)",
                }}
              >
                校验并导入技能
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
