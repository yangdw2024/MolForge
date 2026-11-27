import React, { useState } from "react";
import { Cpu, Play, Download, CheckCircle2 } from "lucide-react";
import { useStudioStore } from "../../store/useStudioStore";
import { molApi } from "../../services/api";
import { FloatingWindow } from "./FloatingWindow";

interface CalculationSetupModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CalculationSetupModal: React.FC<CalculationSetupModalProps> = ({
  isOpen,
  onClose,
}) => {
  const summary = useStudioStore((s) => s.summary);
  const runTask = useStudioStore((s) => s.runTask);

  const [engine, setEngine] = useState<"gaussian" | "orca" | "xtb" | "calchem">("calchem");
  const [jobType, setJobType] = useState<"opt" | "energy" | "freq" | "tddft">("opt");
  const [functional, setFunctional] = useState("B3LYP");
  const [basisSet, setBasisSet] = useState("def2-SVP");
  const [charge, setCharge] = useState(summary?.charge ?? 0);
  const [multiplicity, setMultiplicity] = useState(summary?.multiplicity ?? 1);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [submittedKind, setSubmittedKind] = useState<"ok" | "err">("ok");

  const report = (kind: "ok" | "err", text: string) => {
    setSubmittedKind(kind);
    setSubmitted(text);
  };

  const generateGaussianKeywords = () => {
    let kw = `#p ${functional}/${basisSet}`;
    if (jobType === "opt") kw += " Opt";
    else if (jobType === "freq") kw += " Freq";
    else if (jobType === "tddft") kw += " TD(NStates=6)";
    return kw;
  };

  const generateOrcaKeywords = () => {
    let kw = `! ${functional} ${basisSet}`;
    if (jobType === "opt") kw += " Opt";
    else if (jobType === "freq") kw += " Freq";
    kw += " TightSCF";
    return kw;
  };

  const handleRun = async () => {
    setSubmitted(null);
    if ((engine === "xtb" || engine === "calchem") && (jobType === "freq" || jobType === "tddft")) {
      report("err", `${engine === "xtb" ? "GFN2-xTB" : "CalChem"} 不支持 ${jobType === "freq" ? "振动分析" : "TD-DFT"}，请改用 ORCA / Gaussian 或切换任务类型。`);
      return;
    }
    // 电荷/自旋先真正写入文档（可撤销），后端各引擎统一从文档读取
    try {
      await molApi.setChargeSpin(charge, multiplicity);
    } catch (e) {
      report("err", `电荷/自旋提交失败：${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    if (engine === "calchem") {
      if (functional === "M06-2X") {
        report("err", "CalChem v0.3.0 当前支持 HF / B3LYP / B3LYP5 / PBE / PBE0 / BLYP / CAM-B3LYP / ωB97X-D；M06-2X 请改用 ORCA / Gaussian。");
        return;
      }
      await runTask("CalChem 从头算", async () => {
        const res = await molApi.runCalchem({
          mode: jobType === "opt" ? "opt" : "sp",
          method: functional,
          basis: basisSet,
        });
        if (!res.ok || res.total_energy_hartree == null) {
          report("err", `CalChem 计算未成功：${res.error ?? "无能量输出"}`);
          return;
        }
        const dipNote = res.dipole_magnitude_debye != null ? `, 偶极: ${res.dipole_magnitude_debye.toFixed(3)} D` : "";
        report("ok", `CalChem v0.3.0 纯 Rust 计算完成！基态总能量: ${res.total_energy_hartree.toFixed(6)} Hartree, SCF 收敛: ${res.converged ? "是" : "否"}${dipNote}`);
      });
    } else if (engine === "xtb") {
      await runTask("xTB 结构优化", async () => {
        const res = await molApi.runXtb({
          gfn_level: 2,
          apply_geometry: jobType === "opt",
        });
        if (!res.ok || res.energy_hartree == null) {
          report("err", `GFN2-xTB 计算未成功：${res.error ?? "无能量输出"}${res.stdout_tail ? `\n${res.stdout_tail}` : ""}`);
          return;
        }
        report("ok", `GFN2-xTB 计算完成！单点能: ${res.energy_hartree.toFixed(6)} Hartree${res.converged === false ? "（几何未完全收敛）" : ""}`);
      });
    } else {
      const kw = engine === "gaussian" ? generateGaussianKeywords() : generateOrcaKeywords();
      await runTask(`运行 ${engine.toUpperCase()}`, async () => {
        const res = await molApi.runExternalQc({ engine, keywords: kw });
        if (res.status === "completed") {
          report("ok", `${engine.toUpperCase()} 计算完成${res.energy_hartree != null ? `，总能量 ${res.energy_hartree.toFixed(6)} Hartree` : ""}\n${res.stdout_tail ?? ""}`);
        } else if (res.status === "timeout") {
          report("err", `${engine.toUpperCase()} 超时（600s 护栏）被终止。工作目录: ${res.workdir ?? "—"}\n${res.stdout_tail ?? ""}`);
        } else {
          report("err", `${engine.toUpperCase()} 退出码 ${res.exit_code ?? "?"}，计算未成功。\n${res.stdout_tail ?? ""}`);
        }
      });
    }
  };

  const handleExportInput = async () => {
    try {
      let content: string | undefined;
      let filename: string;
      if (engine === "calchem") {
        const res = await molApi.exportFile("xyz");
        content = res.content;
        filename = res.filename;
      } else {
        const res = await molApi.exportQcInput(engine);
        content = res.content;
        filename = `molforge_${engine}.${engine === "gaussian" ? "gjf" : engine === "xtb" ? "xyz" : "inp"}`;
      }
      if (content) {
        const blob = new Blob([content], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      report("err", `导出失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <FloatingWindow
      id="calculation-setup-layer"
      title={`量子化学与材料计算设置 · ${summary?.name ?? "分子"}`}
      icon={<Cpu size={14} style={{ color: "var(--accent-primary)" }} />}
      isOpen={isOpen}
      onClose={onClose}
      initialPos={{ x: 160, y: 80 }}
      initialSize={{ width: 520, height: 500 }}
      minWidth={440}
      minHeight={360}
    >
      {/* Engine Tabs */}
      <div
        className="flex items-center px-3 pt-2.5 pb-2 border-b gap-1.5 shrink-0"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        {(
          [
            { id: "calchem", label: "🦀 CalChem (纯 Rust 从头算)" },
            { id: "xtb", label: "⚡ GFN2-xTB" },
            { id: "orca", label: "🔬 ORCA 6.x" },
            { id: "gaussian", label: "📘 Gaussian 16" },
          ] as const
        ).map((e) => (
          <button
            key={e.id}
            type="button"
            onClick={() => setEngine(e.id)}
            className="flex-1 h-7 rounded-md text-[11px] font-medium cursor-pointer transition-colors"
            style={{
              backgroundColor: engine === e.id ? "var(--accent-primary)" : "var(--bg-tertiary)",
              color: engine === e.id ? "var(--accent-contrast)" : "var(--text-secondary)",
            }}
          >
            {e.label}
          </button>
        ))}
      </div>

      {/* Configuration Form */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5 text-[12px]">
        {/* Job Type */}
        <div>
          <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--text-secondary)" }}>
            任务类型 (Job Type)
          </label>
          <div className="grid grid-cols-4 gap-1.5">
            {(
              [
                { id: "opt", label: "几何优化 (Opt)" },
                { id: "energy", label: "单点能 (SP)" },
                { id: "freq", label: "振动分析 (Freq)" },
                { id: "tddft", label: "激发态 (TD-DFT)" },
              ] as const
            ).map((j) => (
              <button
                key={j.id}
                type="button"
                onClick={() => setJobType(j.id)}
                className="h-7 rounded border text-[11px] font-medium cursor-pointer transition-colors"
                style={{
                  backgroundColor: jobType === j.id ? "var(--accent-soft)" : "var(--bg-panel)",
                  borderColor: jobType === j.id ? "var(--accent-primary)" : "var(--border-subtle)",
                  color: jobType === j.id ? "var(--accent-primary)" : "var(--text-primary)",
                }}
              >
                {j.label}
              </button>
            ))}
          </div>
        </div>

        {/* Functional & Basis Set */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--text-secondary)" }}>
              泛函 / 理论方法 (Method)
            </label>
            <select
              value={functional}
              onChange={(e) => setFunctional(e.target.value)}
              className="studio-input w-full !h-7 text-[11.5px]"
            >
              <option value="B3LYP">B3LYP (经典杂化)</option>
              <option value="PBE0">PBE0 (高精度共轭)</option>
              <option value="CAM-B3LYP">CAM-B3LYP (长程分离杂化)</option>
              <option value="wB97X-D">ωB97X-D (长程校正)</option>
              <option value="M06-2X">M06-2X (主客体色散 · ORCA/Gaussian)</option>
              <option value="HF">Hartree-Fock (自洽场)</option>
              <option value="PBE">PBE (纯泛函)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--text-secondary)" }}>
              基组 (Basis Set)
            </label>
            <select
              value={basisSet}
              onChange={(e) => setBasisSet(e.target.value)}
              className="studio-input w-full !h-7 text-[11.5px]"
            >
              <option value="def2-SVP">def2-SVP (平衡二裂度)</option>
              <option value="def2-TZVP">def2-TZVP (高精度三裂度)</option>
              <option value="6-31G*">6-31G* (Pople 双分裂)</option>
              <option value="6-311+G**">6-311+G** (弥散极化)</option>
              <option value="STO-3G">STO-3G (极小基组 · 极速测试)</option>
            </select>
          </div>
        </div>

        {/* Charge & Multiplicity */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--text-secondary)" }}>
              分子净电荷 (Charge)
            </label>
            <input
              type="number"
              value={charge}
              onChange={(e) => setCharge(parseInt(e.target.value, 10) || 0)}
              className="studio-input w-full !h-7 mono-num"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--text-secondary)" }}>
              自旋多重度 (2S+1)
            </label>
            <input
              type="number"
              min={1}
              value={multiplicity}
              onChange={(e) => setMultiplicity(Math.max(1, parseInt(e.target.value, 10) || 1))}
              className="studio-input w-full !h-7 mono-num"
            />
          </div>
        </div>

        {/* Generated Command / Keywords Preview */}
        <div>
          <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--text-secondary)" }}>
            输入关键字预览
          </label>
          <div
            className="p-2 rounded-lg border mono-num text-[11px] break-all select-text"
            style={{ backgroundColor: "var(--bg-primary)", borderColor: "var(--border-subtle)", color: "var(--accent-primary)" }}
          >
            {engine === "gaussian" && generateGaussianKeywords()}
            {engine === "orca" && generateOrcaKeywords()}
            {engine === "xtb" && `xtb molecule.xyz${jobType === "opt" ? " --opt" : ""} --gfn 2 --chrg ${charge} --uhf ${multiplicity - 1}`}
            {engine === "calchem" && `calchem::run_calchem(mol, "${functional}", "${basisSet}", chrg=${charge}, mult=${multiplicity}, opt=${jobType === "opt"})`}
          </div>
        </div>

        {submitted && (
          <div
            className="p-2.5 rounded-lg border text-[11px] leading-relaxed flex items-start gap-2"
            style={{
              backgroundColor: submittedKind === "ok" ? "var(--accent-soft)" : "rgba(248,113,113,0.12)",
              borderColor: submittedKind === "ok" ? "var(--accent-primary)" : "#F87171",
              color: "var(--text-primary)",
            }}
          >
            <CheckCircle2 size={15} style={{ color: submittedKind === "ok" ? "var(--accent-primary)" : "#F87171", marginTop: 2, flexShrink: 0 }} />
            <div className="overflow-auto max-h-24 mono-num whitespace-pre-wrap">{submitted}</div>
          </div>
        )}
      </div>

      {/* Footer Actions */}
      <div
        className="h-11 px-4 border-t flex items-center justify-between shrink-0"
        style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-panel)" }}
      >
        <button
          type="button"
          onClick={() => void handleExportInput()}
          className="studio-btn !h-7 text-[11.5px]"
          title="导出计算输入文件"
        >
          <Download size={12} />
          <span>导出输入文件</span>
        </button>

        <button
          type="button"
          onClick={() => void handleRun()}
          className="studio-btn studio-btn-primary !h-7 text-[11.5px]"
        >
          <Play size={12} />
          <span>立即运行计算</span>
        </button>
      </div>
    </FloatingWindow>
  );
};
