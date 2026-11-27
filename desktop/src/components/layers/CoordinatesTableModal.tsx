import React, { useState } from "react";
import { Table, Copy, Check } from "lucide-react";
import { useStudioStore } from "../../store/useStudioStore";
import { molApi } from "../../services/api";
import { FloatingWindow } from "./FloatingWindow";

interface CoordinatesTableModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CoordinatesTableModal: React.FC<CoordinatesTableModalProps> = ({
  isOpen,
  onClose,
}) => {
  const summary = useStudioStore((s) => s.summary);
  const atoms2d = useStudioStore((s) => s.atoms2d);
  const selectedIndices = useStudioStore((s) => s.selectedIndices);
  const setSelectedIndices = useStudioStore((s) => s.setSelectedIndices);
  const runTask = useStudioStore((s) => s.runTask);
  const [copied, setCopied] = useState(false);

  const atoms = atoms2d?.atoms ?? [];

  const handleCopyXyz = () => {
    if (atoms.length === 0) return;
    const lines = [
      `${atoms.length}`,
      `${summary?.name || "MolForge"} | ${summary?.formula || ""}`,
    ];
    for (const a of atoms) {
      lines.push(`${a.symbol.padEnd(2)}  ${a.x.toFixed(4).padStart(10)}  ${a.y.toFixed(4).padStart(10)}  ${a.z.toFixed(4).padStart(10)}`);
    }
    void navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <FloatingWindow
      id="coordinates-layer"
      title={`笛卡尔空间坐标表 · ${summary?.name ?? "分子"} (${atoms.length} 原子)`}
      icon={<Table size={14} style={{ color: "var(--accent-primary)" }} />}
      isOpen={isOpen}
      onClose={onClose}
      initialPos={{ x: 120, y: 100 }}
      initialSize={{ width: 520, height: 460 }}
      minWidth={400}
      minHeight={280}
      headerExtra={
        <button
          type="button"
          onClick={handleCopyXyz}
          className="h-6 px-2 rounded text-[11px] font-medium flex items-center gap-1 cursor-pointer transition-colors"
          style={{
            backgroundColor: copied ? "var(--semantic-success)" : "var(--bg-tertiary)",
            color: copied ? "#ffffff" : "var(--text-secondary)",
          }}
          title="复制为标准 XYZ 坐标格式"
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          <span>{copied ? "已复制 XYZ" : "复制 XYZ"}</span>
        </button>
      }
    >
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse text-left text-[11.5px] mono-num">
          <thead
            className="sticky top-0 z-10 border-b select-none"
            style={{
              backgroundColor: "var(--bg-secondary)",
              borderColor: "var(--border-subtle)",
              color: "var(--text-muted)",
            }}
          >
            <tr>
              <th className="py-1.5 px-3 font-medium w-12">#</th>
              <th className="py-1.5 px-3 font-medium w-16">元素</th>
              <th className="py-1.5 px-3 font-medium">X (Å)</th>
              <th className="py-1.5 px-3 font-medium">Y (Å)</th>
              <th className="py-1.5 px-3 font-medium">Z (Å)</th>
              <th className="py-1.5 px-3 font-medium">电荷</th>
            </tr>
          </thead>
          <tbody className="divide-y" style={{ borderColor: "var(--border-subtle)" }}>
            {atoms.map((a) => {
              const isSelected = selectedIndices.includes(a.index);
              const colorStr = Array.isArray(a.color)
                ? `rgb(${a.color[0]}, ${a.color[1]}, ${a.color[2]})`
                : (a.color || "var(--accent-primary)");
              return (
                <tr
                  key={a.index}
                  onClick={() => setSelectedIndices([a.index])}
                  className="cursor-pointer transition-colors hover:bg-[var(--bg-tertiary)]"
                  style={{
                    backgroundColor: isSelected ? "var(--accent-soft)" : "transparent",
                    color: isSelected ? "var(--accent-primary)" : "var(--text-primary)",
                  }}
                >
                  <td className="py-1.5 px-3 text-[11px] opacity-60">#{a.index}</td>
                  <td className="py-1.5 px-3 font-semibold">
                    <span
                      className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle"
                      style={{ backgroundColor: colorStr }}
                    />
                    {a.symbol} ({a.atomic_num})
                  </td>
                  <td className="py-1.5 px-3">{a.x.toFixed(4)}</td>
                  <td className="py-1.5 px-3">{a.y.toFixed(4)}</td>
                  <td className="py-1.5 px-3">{a.z.toFixed(4)}</td>
                  <td className="py-1.5 px-3 text-[10.5px]">
                    {a.formal_charge !== 0 ? (
                      <span className="font-semibold" style={{ color: a.formal_charge > 0 ? "#F87171" : "#60A5FA" }}>
                        {a.formal_charge > 0 ? `+${a.formal_charge}` : a.formal_charge}
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>0</span>
                    )}
                    {isSelected && <span className="ml-1.5 font-semibold text-[var(--accent-primary)]">选中</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div
        className="h-8 px-3 border-t flex items-center justify-between text-[11px] shrink-0"
        style={{
          borderColor: "var(--border-subtle)",
          backgroundColor: "var(--bg-panel)",
          color: "var(--text-muted)",
        }}
      >
        <span>
          共 {atoms.length} 个原子 · 点击行可高亮视口中的原子
        </span>
        <button
          type="button"
          onClick={() => void runTask("3D 力场优化", () => molApi.clean3D())}
          className="hover:underline cursor-pointer text-[var(--accent-primary)]"
        >
          力场重排坐标
        </button>
      </div>
    </FloatingWindow>
  );
};
