import React, { useEffect, useState } from "react";
import { Check, Cpu, FolderOpen, KeyRound, Monitor, RefreshCw, RotateCcw, ShieldCheck } from "lucide-react";
import { molApi } from "../services/api";
import { useStudioStore } from "../store/useStudioStore";
import type { LlmPreferences } from "../types/studio";

export const SettingsView: React.FC = () => {
  const theme = useStudioStore((s) => s.theme);
  const setTheme = useStudioStore((s) => s.setTheme);
  const reducedMotion = useStudioStore((s) => s.reducedMotion);
  const setReducedMotion = useStudioStore((s) => s.setReducedMotion);
  const uiDensity = useStudioStore((s) => s.uiDensity);
  const setUiDensity = useStudioStore((s) => s.setUiDensity);
  const autosaveEnabled = useStudioStore((s) => s.autosaveEnabled);
  const setAutosaveEnabled = useStudioStore((s) => s.setAutosaveEnabled);
  const resetWorkspaceLayout = useStudioStore((s) => s.resetWorkspaceLayout);
  const bridgeConnected = useStudioStore((s) => s.bridgeConnected);
  const bridgeVersion = useStudioStore((s) => s.bridgeVersion);
  const enginesStatus = useStudioStore((s) => s.enginesStatus);
  const refreshEngines = useStudioStore((s) => s.refreshEngines);
  const pushNotification = useStudioStore((s) => s.pushNotification);
  const refreshScene = useStudioStore((s) => s.refreshScene);

  const [llmPrefs, setLlmPrefs] = useState<LlmPreferences | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [newKey, setNewKey] = useState("");
  const [savedFlag, setSavedFlag] = useState(false);

  useEffect(() => {
    void molApi.getPreferences().then((p) => {
      setLlmPrefs(p);
      setBaseUrl(p.base_url);
      setModelName(p.model);
    }).catch(() => {});
  }, []);

  const handleSaveLlm = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await molApi.savePreferences({
        base_url: baseUrl.trim(),
        model: modelName.trim(),
        ...(newKey.trim() ? { api_key: newKey.trim() } : {}),
      });
      setNewKey("");
      const latest = await molApi.getPreferences();
      setLlmPrefs(latest);
      setSavedFlag(true);
      setTimeout(() => setSavedFlag(false), 2000);
      pushNotification("success", "本地 AI 副驾驶配置已同步更新");
    } catch (err) {
      pushNotification("error", "保存 AI 配置失败", String(err));
    }
  };

  return (
    <div data-testid="view-settings" className="h-full studio-scroll p-5 space-y-4 max-w-[980px]">
      {/* Theme & Interface */}
      <section className="studio-surface p-4 space-y-3">
        <h2 className="text-[14px] font-semibold flex items-center gap-2">
          <Monitor size={15} style={{ color: "var(--accent-primary)" }} />
          <span>外观主题、缩放与交互偏好</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => setTheme("obsidian")}
            className="studio-inset p-3 text-left cursor-pointer space-y-1"
            style={theme === "obsidian" ? { borderColor: "var(--accent-primary)", backgroundColor: "var(--accent-soft)" } : undefined}
          >
            <div className="flex items-center justify-between font-semibold text-[12.5px]">
              <span>Obsidian Laboratory（深空科研黑）</span>
              {theme === "obsidian" && <Check size={14} style={{ color: "var(--accent-primary)" }} />}
            </div>
            <div className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
              主背景 #0B1220 · 面板 #172336 · 强调色 #31B7A5，适合长时间 3D 建模与谱图观察
            </div>
          </button>

          <button
            type="button"
            onClick={() => setTheme("arctic")}
            className="studio-inset p-3 text-left cursor-pointer space-y-1"
            style={theme === "arctic" ? { borderColor: "var(--accent-primary)", backgroundColor: "var(--accent-soft)" } : undefined}
          >
            <div className="flex items-center justify-between font-semibold text-[12.5px]">
              <span>Arctic Laboratory（极地明亮白）</span>
              {theme === "arctic" && <Check size={14} style={{ color: "var(--accent-primary)" }} />}
            </div>
            <div className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
              独立优化 #F5F7FA / #FFFFFF 高对比度层次与论文白底图表配色
            </div>
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-4 pt-2 border-t text-[12px]" style={{ borderColor: "var(--border-subtle)" }}>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={reducedMotion}
              onChange={(e) => setReducedMotion(e.target.checked)}
            />
            <span>减弱界面过渡动效 (prefers-reduced-motion)</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autosaveEnabled}
              onChange={(e) => setAutosaveEnabled(e.target.checked)}
            />
            <span>启用 45 秒周期 `.mforge` 自动备份与崩溃恢复</span>
          </label>

          <div className="flex items-center gap-1.5">
            <span style={{ color: "var(--text-secondary)" }}>信息密度：</span>
            <select
              value={uiDensity}
              onChange={(e) => setUiDensity(e.target.value as "compact" | "comfortable")}
              className="studio-input !h-7"
            >
              <option value="compact">科研高密度 (Compact)</option>
              <option value="comfortable">舒适大字号 (Comfortable)</option>
            </select>
          </div>

          <button type="button" onClick={resetWorkspaceLayout} className="studio-btn !h-7">
            <RotateCcw size={12} />
            <span>恢复默认工作区布局</span>
          </button>
        </div>
      </section>

      {/* Engine & Security */}
      <section className="studio-surface p-4 space-y-2.5 text-[12px]">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold flex items-center gap-2">
            <ShieldCheck size={15} style={{ color: "var(--accent-primary)" }} />
            <span>Python 科学引擎与桌面沙箱状态</span>
          </h2>
          <button
            type="button"
            onClick={async () => {
              await window.molforgeDesktop?.system.restartBridge();
              await refreshScene();
            }}
            className="studio-btn !h-7"
          >
            <RefreshCw size={12} />
            <span>检测/重启内核桥接</span>
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <div className="studio-inset p-2">
            <div className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>内核状态</div>
            <div className="font-semibold" style={{ color: bridgeConnected ? "var(--accent-primary)" : "var(--semantic-error)" }}>
              {bridgeConnected ? "已连接 (:18765)" : "离线"}
            </div>
          </div>
          <div className="studio-inset p-2">
            <div className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>Bridge 协议</div>
            <div className="mono-num">{bridgeVersion}</div>
          </div>
          <div className="studio-inset p-2">
            <div className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>IPC 沙箱</div>
            <div className="mono-num">contextIsolation + sandbox</div>
          </div>
          <div className="studio-inset p-2">
            <div className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>开源协议</div>
            <div className="mono-num">Apache-2.0</div>
          </div>
        </div>
      </section>

      {/* External Scientific Engines Registry */}
      <section data-testid="engines-registry-section" className="studio-surface p-4 space-y-3 text-[12px]">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold flex items-center gap-2">
            <Cpu size={15} style={{ color: "var(--accent-primary)" }} />
            <span>外部科学计算引擎探测与可执行路径配置 ({enginesStatus.filter((e) => e.available).length}/{enginesStatus.length} 可用)</span>
          </h2>
          <button type="button" onClick={() => void refreshEngines()} className="studio-btn !h-7">
            <RefreshCw size={12} />
            <span>重新扫描本机引擎</span>
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-[11.5px]">
            <thead style={{ backgroundColor: "var(--bg-secondary)", borderBottom: "1px solid var(--border-subtle)" }}>
              <tr style={{ color: "var(--text-secondary)" }}>
                <th className="p-2">科学引擎</th>
                <th className="p-2">状态</th>
                <th className="p-2">检测路径 / 版本诊断</th>
                <th className="p-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {enginesStatus.map((eng) => (
                <tr key={eng.id} className="border-b" style={{ borderColor: "var(--border-subtle)" }}>
                  <td className="p-2 font-medium">{eng.name}</td>
                  <td className="p-2">
                    <span
                      className="px-2 py-0.5 rounded-full text-[10.5px] font-semibold whitespace-nowrap"
                      style={{
                        backgroundColor: eng.available ? "var(--accent-soft)" : "var(--semantic-warning-soft)",
                        color: eng.available ? "var(--accent-primary)" : "var(--semantic-warning)",
                      }}
                    >
                      {eng.available ? "已就绪" : "未检测到"}
                    </span>
                  </td>
                  <td className="p-2 mono-num max-w-[360px] truncate" title={eng.executable_path || eng.diagnostic} style={{ color: "var(--text-secondary)", userSelect: "text" }}>
                    {eng.executable_path || eng.diagnostic}
                  </td>
                  <td className="p-2 text-right">
                    {eng.id !== "calchem" && (
                      <button
                        type="button"
                        onClick={async () => {
                          if (!window.molforgeDesktop) return;
                          const dlg = await window.molforgeDesktop.dialogs.openExecutableFile();
                          if (dlg.cancelled || !dlg.filePath) return;
                          const updated = await molApi.configureEngine(eng.id, dlg.filePath);
                          useStudioStore.setState({ enginesStatus: updated.engines });
                          pushNotification("success", `已配置 ${eng.name} 路径`, dlg.filePath);
                        }}
                        className="studio-btn !h-6 !px-2 text-[11px]"
                      >
                        <FolderOpen size={11} />
                        <span>指定 .exe...</span>
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* AI Copilot Endpoint Configuration */}
      <section className="studio-surface p-4 space-y-3">
        <h2 className="text-[14px] font-semibold flex items-center gap-2">
          <KeyRound size={15} style={{ color: "var(--accent-primary)" }} />
          <span>本地 AI 科研副驾驶端点（保留已有密钥，不回显明文）</span>
        </h2>
        <form onSubmit={handleSaveLlm} className="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-[12px]">
          <label className="space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>OpenAI 兼容 Base URL</span>
            <input type="text" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className="studio-input w-full mono-num" />
          </label>
          <label className="space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>默认模型名称</span>
            <input type="text" value={modelName} onChange={(e) => setModelName(e.target.value)} className="studio-input w-full mono-num" />
          </label>
          <label className="space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>
              新 API Key（当前：{llmPrefs?.has_api_key ? llmPrefs.masked_api_key : "未配置"}，留空保持不变）
            </span>
            <input
              type="password"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="留空即沿用本机已记住密钥..."
              className="studio-input w-full mono-num"
            />
          </label>
          <div className="md:col-span-3 flex items-center justify-end gap-2">
            {savedFlag && <span className="text-[11.5px]" style={{ color: "var(--accent-primary)" }}>✓ 已保存至本机配置</span>}
            <button type="submit" className="studio-btn studio-btn-primary">保存端点设置</button>
          </div>
        </form>
      </section>

      {/* Keyboard Shortcuts Reference */}
      <section className="studio-surface p-4 space-y-2 text-[12px]">
        <h2 className="text-[13.5px] font-semibold">全局快捷键速查</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {[
            ["Ctrl + K", "打开命令面板"],
            ["Ctrl+S / Shift+S", "保存 / 另存工程"],
            ["Ctrl + O", "打开结构或工程"],
            ["Ctrl+Z / Ctrl+Y", "撤销 / 重做步骤"],
            ["V / A / B / R / F / E", "工具切换"],
            ["Shift+左键 / 右键", "3D 平移与旋转"],
          ].map(([key, desc]) => (
            <div key={key} className="studio-inset px-2.5 py-1.5 flex items-center justify-between gap-2">
              <span className="truncate" style={{ color: "var(--text-secondary)" }}>{desc}</span>
              <kbd className="mono-num text-[10.5px] px-1.5 py-0.5 rounded whitespace-nowrap shrink-0" style={{ backgroundColor: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}>
                {key}
              </kbd>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};
