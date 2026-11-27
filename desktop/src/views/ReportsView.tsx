import React, { useMemo, useState } from "react";
import { Download, FileText, FolderDown, PackageCheck, Save } from "lucide-react";
import { molApi } from "../services/api";
import { useStudioStore } from "../store/useStudioStore";

export const ReportsView: React.FC = () => {
  const summary = useStudioStore((s) => s.summary);
  const tbResult = useStudioStore((s) => s.tbResult);
  const lastAnalysisResult = useStudioStore((s) => s.lastAnalysisResult);
  const saveProject = useStudioStore((s) => s.saveProject);
  const pushNotification = useStudioStore((s) => s.pushNotification);

  const [batchInputsText, setBatchInputsText] = useState("");
  const [referencePath, setReferencePath] = useState("");
  const [assetDir, setAssetDir] = useState("");
  const [outputDir, setOutputDir] = useState("D:\\YDW\\MolForge_Scratch\\collaborator_delivery");
  const [packageName, setPackageName] = useState("MolForge_Collaborator_Delivery");
  const [allowHalogenSwap, setAllowHalogenSwap] = useState(true);
  const [runningPack, setRunningPack] = useState(false);
  const [packResult, setPackResult] = useState<{
    zip_path: string;
    zip_verified: boolean;
    molecule_count: number;
    total_files: number;
    manifest_sha256: string;
  } | null>(null);

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

      <section className="studio-surface p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h2 className="text-[13.5px] font-semibold flex items-center gap-2">
            <PackageCheck size={15} style={{ color: "var(--accent-primary)" }} />
            <span>批量 MCS 对齐与一键合作者交付打包器（模块 1B + 模块 4）</span>
          </h2>
          <button
            type="button"
            disabled={runningPack}
            onClick={async () => {
              const paths = batchInputsText
                .split(/\r?\n/)
                .map((s) => s.trim())
                .filter(Boolean);
              if (paths.length === 0) {
                pushNotification("warning", "请至少填入一个结构文件路径", "支持 .xyz / .pdb / .mol / .sdf / .gjf / .fchk，每行一个");
                return;
              }
              setRunningPack(true);
              try {
                const res = await molApi.buildDeliveryPackage({
                  input_paths: paths,
                  output_dir: outputDir.trim(),
                  package_name: packageName.trim() || "MolForge_Collaborator_Delivery",
                  reference_path: referencePath.trim() || undefined,
                  asset_dir: assetDir.trim() || undefined,
                  allow_halogen_swap: allowHalogenSwap,
                });
                setPackResult(res);
                pushNotification("success", "合作者交付压缩包生成并校验通过", res.zip_path);
              } catch (err) {
                pushNotification("error", "生成交付包失败", String(err));
              } finally {
                setRunningPack(false);
              }
            }}
            className="studio-btn studio-btn-primary"
          >
            <PackageCheck size={13} />
            <span>{runningPack ? "打包并校验中..." : "一键生成合作者交付包 (.zip + .xlsx)"}</span>
          </button>
        </div>

        <p className="text-[12px]" style={{ color: "var(--text-secondary)" }}>
          自动按 `LMO/ · 平面性/ · 二面角/ · 偶极矩/ · 静电势/ · origin_datas/` 平铺归类，输出保留双精度原始值的单次取整 `.xlsx` 总表、《看图与分析说明》及 CRC 校验 UTF-8 `.zip`。
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[12px]">
          <label className="space-y-1 md:col-span-2">
            <span style={{ color: "var(--text-muted)" }}>批量分子路径（每行一个，支持 .xyz / .pdb / .mol / .gjf / .fchk）</span>
            <textarea
              rows={3}
              value={batchInputsText}
              onChange={(e) => setBatchInputsText(e.target.value)}
              placeholder={"E:\\data\\A1.fchk\nE:\\data\\A2.fchk"}
              className="studio-input w-full !h-auto py-1.5 mono-num"
            />
          </label>
          <label className="space-y-1">
            <span style={{ color: "var(--text-muted)" }}>MCS 刚体对齐基准分子（可选，不填则各自 Core-First 定向）</span>
            <input
              type="text"
              value={referencePath}
              onChange={(e) => setReferencePath(e.target.value)}
              placeholder="基准分子 .fchk / .xyz / .gjf 路径"
              className="studio-input w-full mono-num"
            />
          </label>
          <label className="space-y-1">
            <span style={{ color: "var(--text-muted)" }}>已有图件目录（可选，自动匹配 *_HOMO.png / *_esp.png 等）</span>
            <input
              type="text"
              value={assetDir}
              onChange={(e) => setAssetDir(e.target.value)}
              placeholder="图件目录路径"
              className="studio-input w-full mono-num"
            />
          </label>
          <label className="space-y-1">
            <span style={{ color: "var(--text-muted)" }}>输出目录</span>
            <input
              type="text"
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
              className="studio-input w-full mono-num"
            />
          </label>
          <div className="grid grid-cols-2 gap-2 items-end">
            <label className="space-y-1">
              <span style={{ color: "var(--text-muted)" }}>交付包名称</span>
              <input
                type="text"
                value={packageName}
                onChange={(e) => setPackageName(e.target.value)}
                className="studio-input w-full mono-num"
              />
            </label>
            <label className="flex items-center gap-1.5 h-8 text-[12px]">
              <input
                type="checkbox"
                checked={allowHalogenSwap}
                onChange={(e) => setAllowHalogenSwap(e.target.checked)}
              />
              <span>MCS 允许 F/Cl/Br 卤素互换</span>
            </label>
          </div>
        </div>

        {packResult && (
          <div
            className="p-3 rounded-lg text-[12px] mono-num space-y-1"
            style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)" }}
          >
            <div>
              归档路径：<span style={{ color: "var(--accent-primary)" }}>{packResult.zip_path}</span>
            </div>
            <div>
              CRC 校验：{packResult.zip_verified ? "PASSED" : "FAILED"} · 分子数：{packResult.molecule_count} · 打包文件数：{packResult.total_files}
            </div>
            <div>MANIFEST SHA-256：{packResult.manifest_sha256}</div>
          </div>
        )}
      </section>
    </div>
  );
};
