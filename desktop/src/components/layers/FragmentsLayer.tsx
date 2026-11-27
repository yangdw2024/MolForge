import React, { useState } from "react";
import { Puzzle, Sparkles } from "lucide-react";
import { molApi } from "../../services/api";
import { useStudioStore } from "../../store/useStudioStore";
import { FloatingWindow } from "./FloatingWindow";

interface FragmentItem {
  id: string;
  nameCn: string;
  nameEn: string;
  formula: string;
  category: "osc" | "geometry" | "rings" | "groups";
  description: string;
  tag: string;
}

const FRAGMENT_ITEMS: FragmentItem[] = [
  // OSC 光伏材料砌块
  {
    id: "carbazole",
    nameCn: "咔唑核心",
    nameEn: "Carbazole",
    formula: "C12H9N",
    category: "osc",
    description: "经典空穴传输与高三线态能级给体共轭单元",
    tag: "OSC 给体",
  },
  {
    id: "fluorene",
    nameCn: "芴核心",
    nameEn: "Fluorene",
    formula: "C13H10",
    category: "osc",
    description: "聚芴类蓝光与宽能隙有机半导体骨架",
    tag: "OSC 骨架",
  },
  {
    id: "bdt",
    nameCn: "苯并二噻吩核心",
    nameEn: "BDT Core",
    formula: "C10H4S2",
    category: "osc",
    description: "高效非富勒烯受体与聚合物给体 (PBDB-T/PM6) 核心骨架",
    tag: "OSC 明星基元",
  },
  {
    id: "pentacene",
    nameCn: "并五苯",
    nameEn: "Pentacene",
    formula: "C22H14",
    category: "osc",
    description: "高迁移率有机薄膜场效应晶体管 (OFET) 基准分子",
    tag: "OFET 基准",
  },

  // 环系模板
  {
    id: "benzene",
    nameCn: "苯环 (6-Ar)",
    nameEn: "Benzene",
    formula: "C6H6",
    category: "rings",
    description: "六元芳香烃基础共轭母核",
    tag: "芳环",
  },
  {
    id: "thiophene",
    nameCn: "噻吩环 (5-S)",
    nameEn: "Thiophene",
    formula: "C4H4S",
    category: "rings",
    description: "高平面性五元含硫富电子杂环",
    tag: "杂环",
  },
  {
    id: "pyrrole",
    nameCn: "吡咯环 (5-N)",
    nameEn: "Pyrrole",
    formula: "C4H5N",
    category: "rings",
    description: "含 NH 孤对电子共轭芳香杂环",
    tag: "杂环",
  },
  {
    id: "furan",
    nameCn: "呋喃环 (5-O)",
    nameEn: "Furan",
    formula: "C4H4O",
    category: "rings",
    description: "五元含氧共轭杂环",
    tag: "杂环",
  },

  // 取代基与基团
  {
    id: "methyl",
    nameCn: "甲基 (-CH3)",
    nameEn: "Methyl",
    formula: "CH3",
    category: "groups",
    description: "四面体 sp3 烷基供电子基",
    tag: "烷基",
  },
  {
    id: "hydroxyl",
    nameCn: "羟基 (-OH)",
    nameEn: "Hydroxyl",
    formula: "OH",
    category: "groups",
    description: "强氢键供体与亲水极性基团",
    tag: "极性",
  },
  {
    id: "carboxyl",
    nameCn: "羧基 (-COOH)",
    nameEn: "Carboxyl",
    formula: "COOH",
    category: "groups",
    description: "配位酸性基团与染料敏化锚定基",
    tag: "酸性/锚定",
  },
  {
    id: "amino",
    nameCn: "氨基 (-NH2)",
    nameEn: "Amino",
    formula: "NH2",
    category: "groups",
    description: "碱性亲核与强供电子共轭基",
    tag: "供电子",
  },
  {
    id: "nitro",
    nameCn: "硝基 (-NO2)",
    nameEn: "Nitro",
    formula: "NO2",
    category: "groups",
    description: "强吸电子共轭共振基团",
    tag: "强吸电子",
  },
  {
    id: "cyano",
    nameCn: "氰基 (-CN)",
    nameEn: "Cyano",
    formula: "CN",
    category: "groups",
    description: "线性拟卤素强吸电子端基 (IC 端基前体)",
    tag: "端基吸电",
  },
  {
    id: "methoxy",
    nameCn: "甲氧基 (-OCH3)",
    nameEn: "Methoxy",
    formula: "CH3O",
    category: "groups",
    description: "烷氧基侧链阻阻基团",
    tag: "醚键",
  },
  {
    id: "fluoro",
    nameCn: "氟取代 (-F)",
    nameEn: "Fluoro",
    formula: "F",
    category: "groups",
    description: "强电负性、弱立体位阻卤化改性基 (PM6/Y6 氟化位)",
    tag: "卤化增效",
  },
  {
    id: "chloro",
    nameCn: "氯取代 (-Cl)",
    nameEn: "Chloro",
    formula: "Cl",
    category: "groups",
    description: "兼具吸电子与大极化率卤化基团 (BTP-eC9 位)",
    tag: "卤化增效",
  },
];

interface FragmentsLayerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const FragmentsLayer: React.FC<FragmentsLayerProps> = ({ isOpen, onClose }) => {
  const [tab, setTab] = useState<"osc" | "rings" | "groups">("osc");
  const selectedIndices = useStudioStore((s) => s.selectedIndices);
  const atoms2d = useStudioStore((s) => s.atoms2d);
  const runTask = useStudioStore((s) => s.runTask);

  const selectedAtomId = (() => {
    if (selectedIndices.length === 0) return undefined;
    const sel = atoms2d?.atoms.find((a) => a.index === selectedIndices[0]);
    return sel?.atom_id;
  })();

  const handleInsert = (fragId: string) => {
    void runTask(`插入片段 ${fragId}`, () =>
      molApi.insertFragment({
        fragment_id: fragId,
        anchor_atom_id: selectedAtomId,
        attach_to_existing: selectedAtomId !== undefined,
      })
    );
  };

  const filtered = FRAGMENT_ITEMS.filter((f) => f.category === tab);

  return (
    <FloatingWindow
      id="fragments-layer"
      title="砌块库与 GaussView 片段"
      icon={<Puzzle size={14} style={{ color: "var(--accent-primary)" }} />}
      isOpen={isOpen}
      onClose={onClose}
      initialPos={{ x: 64, y: 56 }}
      initialSize={{ width: 440, height: 520 }}
    >
      {/* Category Tabs */}
      <div
        className="flex items-center px-3 pt-2.5 pb-2 border-b gap-1.5 shrink-0"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        {[
          { id: "osc", label: "🌟 OSC 光电砌块" },
          { id: "rings", label: "⭕ 常用共轭环" },
          { id: "groups", label: "🧪 取代官能团" },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id as any)}
            className="flex-1 h-7 rounded-md text-[11.5px] font-medium cursor-pointer transition-colors"
            style={{
              backgroundColor: tab === t.id ? "var(--accent-primary)" : "var(--bg-tertiary)",
              color: tab === t.id ? "var(--accent-contrast)" : "var(--text-secondary)",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Target Anchor Status */}
      <div
        className="px-3 py-1.5 border-b text-[11px] flex items-center justify-between shrink-0"
        style={{
          backgroundColor: selectedAtomId !== undefined ? "var(--accent-soft)" : "transparent",
          borderColor: "var(--border-subtle)",
          color: selectedAtomId !== undefined ? "var(--accent-primary)" : "var(--text-muted)",
        }}
      >
        <span>
          {selectedAtomId !== undefined
            ? `接枝锚点: 原子 #${selectedAtomId} (点击片段将自动共价成键)`
            : "未选中原子: 点击片段将作为独立分子放置于画布中"}
        </span>
        {selectedAtomId !== undefined && (
          <span className="mono-num font-semibold text-[10px]">ATTACH MODE</span>
        )}
      </div>

      {/* Grid of Fragments */}
      <div className="flex-1 overflow-y-auto p-3 grid grid-cols-2 gap-2">
        {filtered.map((item) => (
          <div
            key={item.id}
            className="p-2.5 rounded-xl border flex flex-col justify-between transition-all hover:border-[var(--accent-primary)] group cursor-pointer"
            style={{
              backgroundColor: "var(--bg-panel)",
              borderColor: "var(--border-subtle)",
            }}
            onClick={() => handleInsert(item.id)}
          >
            <div>
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className="font-semibold text-[12px] truncate" style={{ color: "var(--text-primary)" }}>
                  {item.nameCn}
                </span>
                <span
                  className="text-[9.5px] px-1 py-0.5 rounded font-medium shrink-0"
                  style={{ backgroundColor: "var(--bg-secondary)", color: "var(--accent-primary)" }}
                >
                  {item.tag}
                </span>
              </div>
              <div className="mono-num text-[11px] opacity-75 mb-1" style={{ color: "var(--text-muted)" }}>
                {item.formula} · {item.nameEn}
              </div>
              <p className="text-[10.5px] leading-relaxed line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                {item.description}
              </p>
            </div>

            <button
              type="button"
              className="mt-2.5 w-full h-6 rounded-md text-[11px] font-medium flex items-center justify-center gap-1 cursor-pointer transition-colors group-hover:bg-[var(--accent-primary)] group-hover:text-[var(--accent-contrast)]"
              style={{
                backgroundColor: "var(--bg-tertiary)",
                color: "var(--text-secondary)",
              }}
            >
              <Sparkles size={11} />
              <span>{selectedAtomId !== undefined ? "共价接枝" : "插入画布"}</span>
            </button>
          </div>
        ))}
      </div>
    </FloatingWindow>
  );
};
