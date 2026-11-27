import React, { useMemo } from "react";
import { Download, FileText, FolderDown, Save } from "lucide-react";
import { molApi } from "../services/api";
import { useStudioStore } from "../store/useStudioStore";

export const ReportsView: React.FC = () => {
  const summary = useStudioStore((s) => s.summary);
  const tbResult = useStudioStore((s) => s.tbResult);
  const lastAnalysisResult = useStudioStore((s) => s.lastAnalysisResult);
  const saveProject = useStudioStore((s) => s.saveProject);
  const pushNotification = useStudioStore((s) => s.pushNotification);

  const reportMarkdown = useMemo(() => {
    const lines = [
      `# MolForge Studio 科研工作报告`,
      ``,
      `- 生成时间：${new Date().toLocaleString("zh-CN")}`,
      `- 分子/工程名称：${summary?.name ?? "未加载"}`,
      `- 化学式：${summary?.formula ?? "—"}`,
      `- 分子量：${summary?.molecular_weight != null ? `${summary.molecular_weight} Da` : "—"}`,
      `- 原子数 / 化学键数：${summary?.num_atoms ?? 0} / ${summary?.num_bonds ?? 0}`,
      `- 净电荷 / 自旋态：${summary?.charge ?? 0} / ${summary?.spin_label ?? "—"}`,
      `- 几何形态 / 点群：${summary?.geometry_label ?? "—"} (${summary?.point_group ?? "—"})`,
      ``,
    ];

    if (tbResult && typeof tbResult.homo_ev === "number") {
      lines.push(
        `## Tight-Binding 前线分子轨道结果`,
        `- HOMO: ${tbResult.homo_ev.toFixed(4)} eV`,
        `- LUMO: ${tbResult.lumo_ev?.toFixed(4) ?? "—"} eV`,
        `- 能隙 Eg: ${tbResult.gap_ev?.toFixed(4) ?? "—"} eV`,
        ``
      );
    }

    if (lastAnalysisResult) {
      lines.push(
        `## 最新分析结果 (${lastAnalysisResult.analysis_id}: ${lastAnalysisResult.title})`,
        `- 执行状态：${lastAnalysisResult.status}`,
        `- 摘要：${lastAnalysisResult.summary}`,
        `\`\`\`json`,
        JSON.stringify(lastAnalysisResult.metrics, null, 2),
        `\`\`\``,
        ``
      );
    }
    return lines.join("\n");
  }, [summary, tbResult, lastAnalysisResult]);

  const handleExportStructure = async (fmt: "pdb" | "xyz" | "mol" | "gjf" | "rest") => {
    try {
      const res = await molApi.exportFile(fmt);
      if (window.molforgeDesktop) {
        const ext = res.filename.split(".").pop() || fmt;
        const dlg = await window.molforgeDesktop.dialogs.saveFile(res.filename, [
          { name: `${fmt.toUpperCase()} 文件`, extensions: [ext] },
        ]);
        if (dlg.cancelled || !dlg.filePath) return;
        await window.molforgeDesktop.files.writeTextAtomic(dlg.filePath, res.content);
        pushNotification("success", `已导出 ${res.filename}`, dlg.filePath);
      } else {
        const blob = new Blob([res.content], { type: "text/plain;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = res.filename;
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } catch (err) {
      pushNotification("error", `导出 ${fmt} 失败`, String(err));
    }
  };

  const handleExportMarkdown = async () => {
    const fname = `${(summary?.name || "molforge_report").replace(/\s+/g, "_")}.md`;
    if (window.molforgeDesktop) {
      const dlg = await window.molforgeDesktop.dialogs.saveFile(fname, [
        { name: "Markdown 报告 (*.md)", extensions: ["md"] },
      ]);
      if (dlg.cancelled || !dlg.filePath) return;
      await window.molforgeDesktop.files.writeTextAtomic(dlg.filePath, reportMarkdown);
      pushNotification("success", "已保存 Markdown 科研报告", dlg.filePath);
    } else {
      const blob = new Blob([reportMarkdown], { type: "text/markdown;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = fname;
      a.click();
      URL.revokeObjectURL(a.href);
    }
  };

  return (
    <div data-testid="view-reports" className="h-full studio-scroll p-5 space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section className="studio-surface p-4 space-y-3">
          <h2 className="text-[13.5px] font-semibold flex items-center gap-2">
            <Save size={15} style={{ color: "var(--accent-primary)" }} />
            <span>原生 .mforge 工程归档（与原版 PyQt6 100% 互通）</span>
          </h2>
          <p className="text-[12px]" style={{ color: "var(--text-secondary)" }}>
            采用 `.mforge` v1.1 ZIP 规范（含拓扑稳定 ID、2D/3D 坐标帧、SHA-256 校验与原子落盘）。
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void saveProject(false)} className="studio-btn studio-btn-primary">
              <Save size={13} />
              <span>保存当前工程 (Ctrl+S)</span>
            </button>
            <button type="button" onClick={() => void saveProject(true)} className="studio-btn">
              <FolderDown size={13} />
              <span>另存为新工程 (.mforge)...</span>
            </button>
          </div>
        </section>

        <section className="studio-surface p-4 space-y-3">
          <h2 className="text-[13.5px] font-semibold flex items-center gap-2">
            <Download size={15} style={{ color: "var(--accent-primary)" }} />
            <span>结构与量化软件输入导出</span>
          </h2>
          <p className="text-[12px]" style={{ color: "var(--text-secondary)" }}>
            由 MolForge 真实坐标写出器生成标准结构与高精度计算输入文件。
          </p>
          <div className="flex flex-wrap gap-2">
            {(
              [
                { id: "pdb", label: "导出 PDB" },
                { id: "xyz", label: "导出 XYZ" },
                { id: "mol", label: "导出 MOL V2000" },
                { id: "gjf", label: "Gaussian .gjf" },
                { id: "rest", label: "REST ctrl.in" },
              ] as const
            ).map((btn) => (
              <button key={btn.id} type="button" onClick={() => void handleExportStructure(btn.id)} className="studio-btn">
                {btn.label}
              </button>
            ))}
          </div>
        </section>
      </div>

      <section className="studio-surface p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[13.5px] font-semibold flex items-center gap-2">
            <FileText size={15} style={{ color: "var(--accent-primary)" }} />
            <span>汇总科研分析报告预览 (Markdown)</span>
          </h2>
          <button type="button" onClick={() => void handleExportMarkdown()} className="studio-btn studio-btn-primary">
            <Download size={13} />
            <span>导出 Markdown 报告</span>
          </button>
        </div>

        <pre
          className="p-4 rounded-lg mono-num text-[12px] whitespace-pre-wrap"
          style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)", userSelect: "text" }}
        >
          {reportMarkdown}
        </pre>
      </section>
    </div>
  );
};
