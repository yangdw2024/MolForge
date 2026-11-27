import React, { useMemo, useState } from "react";
import {
  Cpu,
  FileCode2,
  FileSpreadsheet,
  FlaskConical,
  Play,
  Search,
  Upload,
} from "lucide-react";
import { molApi } from "../services/api";
import { useStudioStore } from "../store/useStudioStore";
import { EnergyLadderChart } from "../components/charts/EnergyLadderChart";
import { AnalysisPlotChart } from "../components/charts/AnalysisPlotChart";

type EngineTab = "calchem" | "xtb" | "orca_g16" | "multiwfn" | "gromacs";

export const AnalysisView: React.FC = () => {
  const summary = useStudioStore((s) => s.summary);
  const analysisCatalog = useStudioStore((s) => s.analysisCatalog);
  const enginesStatus = useStudioStore((s) => s.enginesStatus);
  const calchemBasisSets = useStudioStore((s) => s.calchemBasisSets);
  const calchemResult = useStudioStore((s) => s.calchemResult);
  const multiwfnResult = useStudioStore((s) => s.multiwfnResult);
  const gromacsResult = useStudioStore((s) => s.gromacsResult);
  const lastAnalysisResult = useStudioStore((s) => s.lastAnalysisResult);
  const tbResult = useStudioStore((s) => s.tbResult);
  const qcParsed = useStudioStore((s) => s.qcParsed);
  const runAndRecordAnalysis = useStudioStore((s) => s.runAndRecordAnalysis);
  const runTightBinding = useStudioStore((s) => s.runTightBinding);
  const submitBackgroundJob = useStudioStore((s) => s.submitBackgroundJob);
  const refreshScene = useStudioStore((s) => s.refreshScene);
  const setRoute = useStudioStore((s) => s.setRoute);
  const pushNotification = useStudioStore((s) => s.pushNotification);
  const recentAnalyses = useStudioStore((s) => s.recentAnalyses);

  const [category, setCategory] = useState("全部");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string>("CORE-01");
  const [qcPreview, setQcPreview] = useState<{ kind: string; content: string } | null>(null);

  const [engineTab, setEngineTab] = useState<EngineTab>("calchem");
  const [ccMethod, setCcMethod] = useState("rhf");
  const [ccBasis, setCcBasis] = useState("sto-3g");
  const [extEngine, setExtEngine] = useState<"orca" | "gaussian">("orca");
  const [extKeywords, setExtKeywords] = useState("! HF STO-3G");
  const [mwfnTask, setMwfnTask] = useState("WFN-12");
  const [gmxTemp, setGmxTemp] = useState(298.15);
  const [gmxSteps, setGmxSteps] = useState(500000);
  const [activeGmxTab, setActiveGmxTab] = useState("minim.mdp");
  const [engineBusy, setEngineBusy] = useState(false);

  const [reorgOpen, setReorgOpen] = useState(false);
  const [reorgCarrier, setReorgCarrier] = useState<"hole" | "electron">("hole");
  const [eNN, setENN] = useState("");
  const [eNI, setENI] = useState("");
  const [eII, setEII] = useState("");
  const [eIN, setEIN] = useState("");
  const [reorgRes, setReorgRes] = useState<{
    lambda1_ev: number;
    lambda2_ev: number;
    lambda_total_ev: number;
    lambda_total_mev: number;
    lambda_total_kcal: number;
  } | null>(null);

  const engineAvailable = (id: string) =>
    enginesStatus.find((e) => e.id === id)?.available ?? false;

  const categories = useMemo(() => {
    const set = new Set<string>(["全部"]);
    for (const item of analysisCatalog) set.add(item.category);
    return Array.from(set);
  }, [analysisCatalog]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return analysisCatalog.filter((it) => {
      if (category !== "全部" && it.category !== category) return false;
      if (!q) return true;
      return (
        it.id.toLowerCase().includes(q) ||
        it.title.toLowerCase().includes(q) ||
        it.engine.toLowerCase().includes(q)
      );
    });
  }, [analysisCatalog, category, search]);

  const selectedItem = useMemo(
    () => analysisCatalog.find((x) => x.id === selectedId) ?? filtered[0] ?? null,
    [analysisCatalog, selectedId, filtered]
  );

  const handleLoadQcFile = async () => {
    if (!window.molforgeDesktop) {
      pushNotification("info", "请在桌面端打开本地 .fchk 或 .log 文件");
      return;
    }
    const dlg = await window.molforgeDesktop.dialogs.openQcLogFile();
    if (dlg.cancelled || !dlg.filePath) return;
    try {
      const parsed = await molApi.parseQcLog(dlg.filePath);
      useStudioStore.setState({ qcParsed: parsed });
      pushNotification("success", `已解析 ${parsed.kind.toUpperCase()} 前线轨道`, `HOMO=${parsed.homo_ev} eV · Eg=${parsed.gap_ev} eV`);
    } catch (err) {
      pushNotification("error", "量化日志解析失败", String(err));
    }
  };

  const handleExportQc = async (kind: "gaussian" | "rest" | "orca" | "xtb") => {
    try {
      const res = await molApi.exportQcInput(kind);
      setQcPreview({ kind: res.engine, content: res.content });
    } catch (err) {
      pushNotification("error", "生成量化输入失败", String(err));
    }
  };

  return (
    <div data-testid="view-analysis" className="h-full flex min-h-0">
      {/* Left: 79 CapabilityResolver Catalog */}
      <aside
        className="w-[300px] shrink-0 border-r flex flex-col min-h-0 p-3 gap-2.5"
        style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border-subtle)" }}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-semibold flex items-center gap-1.5">
            <FlaskConical size={14} style={{ color: "var(--accent-primary)" }} />
            <span>分析方法目录 ({analysisCatalog.length})</span>
          </h2>
        </div>

        <div className="relative">
          <Search size={12.5} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="过滤分析项 (WFN / ESP / OSC)..."
            className="studio-input pl-8 w-full"
          />
        </div>

        <select value={category} onChange={(e) => setCategory(e.target.value)} className="studio-input w-full">
          {categories.map((c) => (
            <option key={c} value={c}>
              专题：{c}
            </option>
          ))}
        </select>

        <div className="flex-1 studio-scroll space-y-1.5 pr-0.5">
          {filtered.map((item) => {
            const active = item.id === selectedItem?.id;
            const ready = item.state === "ready";
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedId(item.id)}
                className="w-full p-2.5 rounded-lg text-left transition-colors cursor-pointer space-y-1"
                style={{
                  backgroundColor: active ? "var(--accent-soft)" : "var(--bg-panel)",
                  border: `1px solid ${active ? "var(--accent-primary)" : "var(--border-subtle)"}`,
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="mono-num text-[11px] font-semibold" style={{ color: "var(--accent-primary)" }}>
                    {item.id}
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.2 rounded"
                    style={{
                      backgroundColor: ready ? "var(--accent-soft)" : "var(--bg-secondary)",
                      color: ready ? "var(--accent-primary)" : "var(--text-muted)",
                    }}
                  >
                    {item.state}
                  </span>
                </div>
                <div className="text-[12px] font-medium leading-snug">{item.title}</div>
                <div className="text-[10.5px] truncate" style={{ color: "var(--text-muted)" }}>
                  {item.engine}
                </div>
              </button>
            );
          })}
        </div>
      </aside>

      {/* Center: Charts, Actions & Results */}
      <div className="flex-1 min-w-0 studio-scroll p-4 space-y-4">
        {/* Top Action Ribbon */}
        <div className="studio-surface p-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="run-tb-btn"
              onClick={() => void runTightBinding()}
              className="studio-btn studio-btn-primary"
            >
              <Play size={13} />
              <span>Tight-Binding 前线轨道实算</span>
            </button>

            {selectedItem && (
              <>
                <button
                  type="button"
                  data-testid="run-selected-analysis-btn"
                  onClick={() => void runAndRecordAnalysis(selectedItem.id)}
                  className="studio-btn"
                >
                  <Play size={13} style={{ color: "var(--accent-primary)" }} />
                  <span>执行 {selectedItem.id}</span>
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void submitBackgroundJob("analysis", `${selectedItem.id} · ${selectedItem.title}`, {
                      analysis_id: selectedItem.id,
                    })
                  }
                  className="studio-btn"
                >
                  <span>加入后台任务</span>
                </button>
              </>
            )}
            <button
              type="button"
              data-testid="run-mpp-btn"
              onClick={() => void runAndRecordAnalysis("PROP-MPP")}
              className="studio-btn"
            >
              <Play size={12.5} style={{ color: "var(--accent-primary)" }} />
              <span>MPP 平面性</span>
            </button>
            <button
              type="button"
              data-testid="run-rdf-btn"
              onClick={() => void runAndRecordAnalysis("MD-RDF")}
              className="studio-btn"
            >
              <Play size={12.5} style={{ color: "var(--accent-primary)" }} />
              <span>RDF 径向分布</span>
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <button type="button" onClick={() => void handleLoadQcFile()} className="studio-btn">
              <Upload size={12.5} />
              <span>读取 .fchk / .log</span>
            </button>
            <button type="button" onClick={() => void handleExportQc("gaussian")} className="studio-btn">
              <FileCode2 size={12.5} />
              <span>生成 .gjf</span>
            </button>
            <button type="button" onClick={() => void handleExportQc("rest")} className="studio-btn">
              <FileCode2 size={12.5} />
              <span>生成 REST ctrl.in</span>
            </button>
            <button type="button" onClick={() => void handleExportQc("orca")} className="studio-btn">
              <FileCode2 size={12.5} />
              <span>生成 ORCA .inp</span>
            </button>
            <button type="button" onClick={() => void handleExportQc("xtb")} className="studio-btn">
              <FileCode2 size={12.5} />
              <span>生成 xtb .xyz</span>
            </button>
          </div>
        </div>

        {/* Selected Analysis Detail Banner */}
        {selectedItem && (
          <div className="studio-surface p-3 flex flex-wrap items-center justify-between gap-2 text-[12px]">
            <div>
              <span className="mono-num font-semibold" style={{ color: "var(--accent-primary)" }}>
                {selectedItem.id}
              </span>{" "}
              <span className="font-semibold">{selectedItem.title}</span>
              <span className="ml-2 text-[11px]" style={{ color: "var(--text-secondary)" }}>
                依赖引擎：{selectedItem.engine}
              </span>
            </div>
            <div className="text-[11.5px]" style={{ color: "var(--text-secondary)" }}>
              {selectedItem.note}
            </div>
          </div>
        )}

        {/* Multi-Engine Execution Deck: CalChem / xTB / ORCA & Gaussian / Multiwfn / GROMACS */}
        <section data-testid="engine-execution-deck" className="studio-surface p-3 space-y-3 text-[12px]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2" style={{ borderColor: "var(--border-subtle)" }}>
            <div className="flex items-center gap-1.5 font-semibold">
              <Cpu size={14} style={{ color: "var(--accent-primary)" }} />
              <span>真实科学计算引擎控制台</span>
            </div>
            <div className="flex flex-wrap items-center gap-1">
              {(
                [
                  { id: "calchem", label: "CalChem 从头算", ok: engineAvailable("calchem") },
                  { id: "xtb", label: "GFN2-xTB 优化", ok: engineAvailable("xtb") },
                  { id: "orca_g16", label: "ORCA / Gaussian", ok: engineAvailable("orca") || engineAvailable("gaussian") },
                  { id: "multiwfn", label: "Multiwfn 波函数", ok: engineAvailable("multiwfn") },
                  { id: "gromacs", label: "GROMACS MD", ok: engineAvailable("gromacs") },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  data-testid={`engine-tab-${tab.id}`}
                  onClick={() => setEngineTab(tab.id)}
                  className="h-7 px-2.5 rounded-md text-[11.5px] flex items-center gap-1.5 cursor-pointer"
                  style={{
                    backgroundColor: engineTab === tab.id ? "var(--accent-soft)" : "var(--bg-secondary)",
                    color: engineTab === tab.id ? "var(--accent-primary)" : "var(--text-secondary)",
                    border: `1px solid ${engineTab === tab.id ? "var(--accent-primary)" : "var(--border-subtle)"}`,
                  }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: tab.ok ? "var(--accent-primary)" : "var(--text-muted)" }}
                  />
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>
          </div>

          {engineTab === "calchem" && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <select value={ccMethod} onChange={(e) => setCcMethod(e.target.value)} className="studio-input !h-7">
                  <option value="rhf">RHF (闭壳层 Hartree-Fock)</option>
                  <option value="b3lyp">B3LYP (VWN-RPA 杂化 DFT)</option>
                  <option value="b3lyp5">B3LYP5 (VWN-5 杂化 DFT)</option>
                  <option value="pbe0">PBE0 (25% HF 杂化 DFT)</option>
                  <option value="pbe">PBE (纯泛函 GGA)</option>
                  <option value="blyp">BLYP (纯泛函 GGA)</option>
                  <option value="cam-b3lyp">CAM-B3LYP (长程分离杂化)</option>
                  <option value="wb97x-d">ωB97X-D (长程分离色散)</option>
                  <option value="uhf">UHF (开壳层非限制 HF)</option>
                  <option value="uks">UKS (开壳层非限制 DFT)</option>
                </select>
                <select value={ccBasis} onChange={(e) => setCcBasis(e.target.value)} className="studio-input !h-7">
                  {calchemBasisSets.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
                <button
                  type="button"
                  data-testid="run-calchem-sp-btn"
                  disabled={engineBusy || !engineAvailable("calchem")}
                  onClick={async () => {
                    setEngineBusy(true);
                    try {
                      const res = await molApi.runCalchem({ mode: "sp", method: ccMethod, basis: ccBasis });
                      useStudioStore.setState({ calchemResult: res });
                      if (res.ok && res.total_energy_hartree != null) {
                        pushNotification("success", "CalChem SCF 计算完成", `E = ${res.total_energy_hartree.toFixed(6)} Hartree`);
                      } else {
                        pushNotification("error", "CalChem SCF 未成功", res.error ?? "无能量输出");
                      }
                    } catch (err) {
                      pushNotification("error", "CalChem SCF 失败", String(err));
                    } finally {
                      setEngineBusy(false);
                    }
                  }}
                  className="studio-btn studio-btn-primary !h-7"
                >
                  <Play size={12} />
                  <span>执行 SCF 单点能</span>
                </button>
                <button
                  type="button"
                  disabled={engineBusy || !engineAvailable("calchem")}
                  onClick={() => {
                    void submitBackgroundJob("calchem_opt", `CalChem 优化 (${ccMethod.toUpperCase()}/${ccBasis})`, {
                      method: ccMethod,
                      basis: ccBasis,
                    });
                    setRoute("jobs");
                  }}
                  className="studio-btn !h-7"
                >
                  <span>提交量子几何优化 (后台)</span>
                </button>
              </div>
              {calchemResult?.ok && (
                <div className="studio-inset p-2.5 grid grid-cols-2 md:grid-cols-4 gap-2 mono-num text-[11.5px]">
                  <div><span style={{ color: "var(--text-muted)" }}>总能量: </span>{calchemResult.total_energy_hartree?.toFixed(6)} Eh</div>
                  <div><span style={{ color: "var(--text-muted)" }}>HOMO: </span>{calchemResult.homo_ev != null ? calchemResult.homo_ev.toFixed(3) : "—"} eV</div>
                  <div><span style={{ color: "var(--text-muted)" }}>LUMO: </span>{calchemResult.lumo_ev != null ? calchemResult.lumo_ev.toFixed(3) : "—"} eV</div>
                  <div><span style={{ color: "var(--text-muted)" }}>偶极 / 基函数: </span>{calchemResult.dipole_magnitude_debye != null ? calchemResult.dipole_magnitude_debye.toFixed(3) : "—"} D / {calchemResult.n_ao ?? "—"}</div>
                </div>
              )}
            </div>
          )}

          {engineTab === "xtb" && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div style={{ color: "var(--text-secondary)" }}>
                调用本机 `xtb.exe` 执行 GFN2-xTB 解析梯度几何优化，收敛后通过 CommandBus 写回 3D 坐标（支持 Ctrl+Z 撤销）。
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  data-testid="run-xtb-opt-btn"
                  disabled={engineBusy || !engineAvailable("xtb")}
                  onClick={async () => {
                    setEngineBusy(true);
                    try {
                      const res = await molApi.runXtb({ gfn_level: 2, apply_geometry: true });
                      await refreshScene();
                      if (res.ok && res.energy_hartree != null) {
                        pushNotification("success", "GFN2-xTB 优化已收敛", `E = ${res.energy_hartree.toFixed(6)} Hartree`);
                      } else {
                        pushNotification("error", "GFN2-xTB 未成功", res.error ?? "无能量输出");
                      }
                    } catch (err) {
                      pushNotification("error", "GFN2-xTB 优化失败", String(err));
                    } finally {
                      setEngineBusy(false);
                    }
                  }}
                  className="studio-btn studio-btn-primary !h-7"
                >
                  <Play size={12} />
                  <span>立即执行 xTB 几何优化</span>
                </button>
              </div>
            </div>
          )}

          {engineTab === "orca_g16" && (
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={extEngine}
                onChange={(e) => {
                  const v = e.target.value as "orca" | "gaussian";
                  setExtEngine(v);
                  setExtKeywords(v === "orca" ? "! HF STO-3G" : "#p HF/STO-3G");
                }}
                className="studio-input !h-7"
              >
                <option value="orca">ORCA 6.1.1 ({engineAvailable("orca") ? "已就绪" : "未找到"})</option>
                <option value="gaussian">Gaussian 16 ({engineAvailable("gaussian") ? "已就绪" : "未找到"})</option>
              </select>
              <input
                type="text"
                value={extKeywords}
                onChange={(e) => setExtKeywords(e.target.value)}
                className="studio-input !h-7 flex-1 min-w-[200px] mono-num"
                placeholder="输入方法与基组关键字..."
              />
              <button
                type="button"
                disabled={!engineAvailable(extEngine)}
                onClick={() => {
                  void submitBackgroundJob(
                    extEngine === "orca" ? "orca_sp" : "gaussian_sp",
                    `${extEngine.toUpperCase()} · ${extKeywords} (${summary?.name || ""})`,
                    { keywords: extKeywords }
                  );
                  setRoute("jobs");
                }}
                className="studio-btn studio-btn-primary !h-7"
              >
                <Play size={12} />
                <span>提交至后台实算队列</span>
              </button>
            </div>
          )}

          {engineTab === "multiwfn" && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <select value={mwfnTask} onChange={(e) => setMwfnTask(e.target.value)} className="studio-input !h-7">
                  <option value="WFN-12">WFN-12 · NCI/RDG 弱相互作用散点（坐标=promolecular；选 .fchk/.wfn=波函数）</option>
                  <option value="WFN-01">WFN-01 · 定量表面静电势 ESP（选 .fchk/.wfn/.molden，输出 Vs/MPI/面积）</option>
                  <option value="WFN-06">WFN-06 · Mayer 键级实算（选 .fchk/.wfn/.molden）</option>
                  <option value="WFN-08">WFN-08 · ADCH 原子电荷实算（选 .fchk/.wfn/.molden）</option>
                </select>
                <button
                  type="button"
                  data-testid="run-multiwfn-doc-btn"
                  disabled={engineBusy || !engineAvailable("multiwfn")}
                  onClick={async () => {
                    setEngineBusy(true);
                    try {
                      let inpFile: string | undefined;
                      if (mwfnTask !== "WFN-12" && window.molforgeDesktop) {
                        const dlg = await window.molforgeDesktop.dialogs.openQcLogFile();
                        if (dlg.cancelled || !dlg.filePath) {
                          setEngineBusy(false);
                          return;
                        }
                        inpFile = dlg.filePath;
                      }
                      const res = await molApi.runMultiwfn({ analysis_id: mwfnTask, input_file: inpFile });
                      useStudioStore.setState({
                        multiwfnResult: res,
                        lastAnalysisResult: {
                          analysis_id: res.analysis_id,
                          title: `Multiwfn 3.8 实算 (${res.input_file})`,
                          status: res.ok ? "completed" : "failed",
                          summary: res.message,
                          metrics: res.metrics,
                          plot_x: res.plot_x,
                          plot_y: res.plot_y,
                          x_label: res.x_label,
                          y_label: res.y_label,
                        },
                      });
                      pushNotification(res.ok ? "success" : "error", res.ok ? "Multiwfn 实算完成" : "Multiwfn 未产出真实数据", res.message);
                    } catch (err) {
                      pushNotification("error", "Multiwfn 运行失败", String(err));
                    } finally {
                      setEngineBusy(false);
                    }
                  }}
                  className="studio-btn studio-btn-primary !h-7"
                >
                  <Play size={12} />
                  <span>调用 Multiwfn.exe 实算</span>
                </button>
              </div>
              {multiwfnResult && (
                <div className="studio-inset p-2 mono-num text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {multiwfnResult.message} · {multiwfnResult.stdout_tail}
                </div>
              )}
            </div>
          )}

          {engineTab === "gromacs" && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1">
                  <span>温度 (K)</span>
                  <input type="number" value={gmxTemp} onChange={(e) => setGmxTemp(Number(e.target.value))} className="studio-input !h-7 w-20 mono-num" />
                </label>
                <label className="flex items-center gap-1">
                  <span>MD 步数</span>
                  <input type="number" value={gmxSteps} onChange={(e) => setGmxSteps(Number(e.target.value))} className="studio-input !h-7 w-24 mono-num" />
                </label>
                <button
                  type="button"
                  onClick={async () => {
                    const res = await molApi.generateGromacs({ temp_k: gmxTemp, nsteps_md: gmxSteps });
                    useStudioStore.setState({ gromacsResult: res });
                    pushNotification("success", "已生成 GROMACS MDP 与跑批脚本");
                  }}
                  className="studio-btn studio-btn-primary !h-7"
                >
                  <FileCode2 size={12} />
                  <span>生成 .mdp 与 gmx.exe 运行脚本</span>
                </button>
              </div>
              {gromacsResult && (
                <div className="space-y-1.5">
                  <div className="flex gap-1">
                    {Object.keys(gromacsResult.files).map((fname) => (
                      <button
                        key={fname}
                        type="button"
                        onClick={() => setActiveGmxTab(fname)}
                        className="studio-btn !h-6 !px-2 text-[11px]"
                        style={activeGmxTab === fname ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
                      >
                        {fname}
                      </button>
                    ))}
                  </div>
                  <pre className="p-2.5 rounded-lg mono-num text-[11px] max-h-[150px] studio-scroll" style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)", userSelect: "text" }}>
                    {gromacsResult.files[activeGmxTab] || ""}
                  </pre>
                </div>
              )}
            </div>
          )}
        </section>

        {/* OSC Energy Ladder */}
        <EnergyLadderChart
          tbResult={tbResult}
          qcParsed={qcParsed}
          activeName={summary?.name || "当前分子"}
        />

        {/* CapabilityResolver Plot */}
        <AnalysisPlotChart result={lastAnalysisResult} />

        {/* Structured Metrics Table */}
        {(lastAnalysisResult?.metrics || tbResult?.transitions) && (
          <div className="studio-surface p-3 space-y-2">
            <div className="flex items-center gap-1.5 text-[12.5px] font-semibold">
              <FileSpreadsheet size={14} style={{ color: "var(--accent-primary)" }} />
              <span>结构化量化与分析数据表</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {tbResult && typeof tbResult.homo_ev === "number" && (
                <>
                  <div className="studio-inset p-2">
                    <div className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>TB HOMO</div>
                    <div className="mono-num text-[13px] font-semibold">{tbResult.homo_ev.toFixed(3)} eV</div>
                  </div>
                  <div className="studio-inset p-2">
                    <div className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>TB LUMO</div>
                    <div className="mono-num text-[13px] font-semibold">{tbResult.lumo_ev?.toFixed(3)} eV</div>
                  </div>
                  <div className="studio-inset p-2">
                    <div className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>光学/带隙 Eg</div>
                    <div className="mono-num text-[13px] font-semibold">{tbResult.gap_ev?.toFixed(3)} eV</div>
                  </div>
                </>
              )}
              {lastAnalysisResult &&
                Object.entries(lastAnalysisResult.metrics).map(([k, v]) => (
                  <div key={k} className="studio-inset p-2">
                    <div className="text-[10.5px] truncate" style={{ color: "var(--text-muted)" }}>{k}</div>
                    <div className="mono-num text-[12.5px] font-semibold truncate" title={String(v)}>
                      {typeof v === "object" ? JSON.stringify(v) : String(v)}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* OSC Reorganization Energy (4-point) Calculator */}
        <section className="studio-surface p-3 space-y-2.5 text-[12px]">
          <div className="flex items-center justify-between">
            <span className="font-semibold">OSC 四点法载流子重组能计算器 (λ = λ₁ + λ₂)</span>
            <button
              type="button"
              onClick={() => setReorgOpen((v) => !v)}
              className="studio-btn !h-7 text-[11px]"
            >
              {reorgOpen ? "收起" : "展开四点法计算"}
            </button>
          </div>
          {reorgOpen && (
            <div className="space-y-2.5 pt-1 border-t" style={{ borderColor: "var(--border-subtle)" }}>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                <select
                  value={reorgCarrier}
                  onChange={(e) => setReorgCarrier(e.target.value as "hole" | "electron")}
                  className="studio-input !h-7"
                >
                  <option value="hole">空穴重组能 (λh)</option>
                  <option value="electron">电子重组能 (λe)</option>
                </select>
                <input value={eNN} onChange={(e) => setENN(e.target.value)} placeholder="E(N@N) Hartree" className="studio-input !h-7 mono-num" />
                <input value={eNI} onChange={(e) => setENI(e.target.value)} placeholder="E(N@I) Hartree" className="studio-input !h-7 mono-num" />
                <input value={eII} onChange={(e) => setEII(e.target.value)} placeholder="E(I@I) Hartree" className="studio-input !h-7 mono-num" />
                <input value={eIN} onChange={(e) => setEIN(e.target.value)} placeholder="E(I@N) Hartree" className="studio-input !h-7 mono-num" />
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className="studio-btn studio-btn-primary !h-7"
                  onClick={async () => {
                    const nums = [Number(eNN), Number(eNI), Number(eII), Number(eIN)];
                    if (nums.some((x) => !Number.isFinite(x) || x === 0)) {
                      pushNotification("error", "请输入 4 个有效 Hartree 能量值");
                      return;
                    }
                    try {
                      const res = await molApi.computeReorganizationEnergy({
                        carrier: reorgCarrier,
                        e_n_n: nums[0],
                        e_n_i: nums[1],
                        e_i_i: nums[2],
                        e_i_n: nums[3],
                      });
                      setReorgRes(res);
                      pushNotification("success", "重组能计算完成", `λtot = ${res.lambda_total_mev.toFixed(1)} meV`);
                    } catch (err) {
                      pushNotification("error", "重组能计算失败", String(err));
                    }
                  }}
                >
                  <Play size={12} />
                  <span>计算 λ₁ / λ₂ / λtot</span>
                </button>
                {reorgRes && (
                  <div className="mono-num text-[11.5px]" style={{ color: "var(--accent-primary)" }}>
                    λ₁ = {reorgRes.lambda1_ev.toFixed(4)} eV · λ₂ = {reorgRes.lambda2_ev.toFixed(4)} eV · λtot ={" "}
                    {reorgRes.lambda_total_ev.toFixed(4)} eV ({reorgRes.lambda_total_mev.toFixed(1)} meV /{" "}
                    {reorgRes.lambda_total_kcal.toFixed(2)} kcal/mol)
                  </div>
                )}
              </div>
            </div>
          )}
        </section>

        {/* QC Input File Preview */}
        {qcPreview && (
          <div className="studio-surface p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12.5px] font-semibold">
                生成的{" "}
                {qcPreview.kind === "rest"
                  ? "复旦 REST ctrl.in"
                  : qcPreview.kind === "orca"
                  ? "ORCA .inp"
                  : qcPreview.kind === "xtb"
                  ? "GFN2-xTB .xyz"
                  : "Gaussian .gjf"}{" "}
                计算脚本预览
              </span>
              <button
                type="button"
                className="studio-btn !h-7"
                onClick={() => {
                  void navigator.clipboard.writeText(qcPreview.content);
                  pushNotification("success", "已复制计算输入脚本至剪贴板");
                }}
              >
                复制内容
              </button>
            </div>
            <pre
              className="p-3 rounded-lg text-[11.5px] mono-num max-h-[220px] studio-scroll"
              style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)", userSelect: "text" }}
            >
              {qcPreview.content}
            </pre>
          </div>
        )}

        {/* Session Run History */}
        {recentAnalyses.length > 0 && (
          <div className="studio-surface p-3 space-y-1.5">
            <div className="text-[12px] font-semibold">本次会话分析记录</div>
            <div className="space-y-1">
              {recentAnalyses.slice(0, 6).map((r, idx) => (
                <div key={idx} className="flex items-center justify-between text-[11.5px] py-1 border-b last:border-b-0" style={{ borderColor: "var(--border-subtle)" }}>
                  <span>
                    <span className="mono-num font-semibold" style={{ color: "var(--accent-primary)" }}>{r.analysisId}</span>{" "}
                    {r.title} ({r.moleculeName})
                  </span>
                  <span className="mono-num text-[11px]" style={{ color: "var(--text-muted)" }}>{r.status} · {r.timestamp}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
