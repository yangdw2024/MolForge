import React, { useMemo, useState } from "react";
import {
  ArrowDownUp,
  Check,
  Columns3,
  Copy,
  Download,
  Grid2x2,
  List,
  Plus,
  Search,
  Upload,
} from "lucide-react";
import { molApi } from "../services/api";
import { useStudioStore } from "../store/useStudioStore";
import type { LibraryMoleculeEntry } from "../types/studio";
import { StructureThumbnail2D } from "../components/common/StructureThumbnail2D";

export const LibraryView: React.FC = () => {
  const libraryItems = useStudioStore((s) => s.libraryItems);
  const customLibraryItems = useStudioStore((s) => s.customLibraryItems);
  const addCustomLibraryItems = useStudioStore((s) => s.addCustomLibraryItems);
  const runTask = useStudioStore((s) => s.runTask);
  const pushNotification = useStudioStore((s) => s.pushNotification);

  const [viewMode, setViewMode] = useState<"table" | "cards">("table");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("全部");
  const [sortBy, setSortBy] = useState<"name" | "mw" | "atoms">("name");
  const [sortAsc, setSortAsc] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("Naphthalene,c1ccc2ccccc2c1\nAnthracene,c1ccc2cc3ccccc3cc2c1");
  const [showCols, setShowCols] = useState({ formula: true, mw: true, atoms: true, smiles: true });

  const allItems = useMemo<LibraryMoleculeEntry[]>(
    () => [...customLibraryItems, ...libraryItems],
    [customLibraryItems, libraryItems]
  );

  const categories = useMemo(() => {
    const s = new Set<string>(["全部"]);
    for (const it of allItems) s.add(it.category);
    return Array.from(s);
  }, [allItems]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = allItems.filter((it) => {
      if (categoryFilter !== "全部" && it.category !== categoryFilter) return false;
      if (!q) return true;
      return (
        it.name.toLowerCase().includes(q) ||
        it.formula.toLowerCase().includes(q) ||
        it.smiles.toLowerCase().includes(q) ||
        it.category.toLowerCase().includes(q)
      );
    });
    list.sort((a, b) => {
      const cmp =
        sortBy === "mw"
          ? a.molecular_weight - b.molecular_weight
          : sortBy === "atoms"
          ? a.num_atoms - b.num_atoms
          : a.name.localeCompare(b.name, "zh-CN");
      return sortAsc ? cmp : -cmp;
    });
    return list;
  }, [allItems, search, categoryFilter, sortBy, sortAsc]);

  const handleLoadItem = (item: LibraryMoleculeEntry) => {
    const isBuiltIn = libraryItems.some((x) => x.id === item.id);
    if (isBuiltIn) {
      void runTask(`载入 ${item.name}`, () => molApi.loadPreset(item.id), true);
    } else {
      void runTask(`载入 ${item.name}`, () => molApi.buildSmiles(item.smiles, item.name), true);
    }
  };

  const handleBatchImport = async () => {
    const lines = importText
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    const reqItems = lines.map((line, i) => {
      const parts = line.split(/[,\t]+/);
      return parts.length >= 2
        ? { name: parts[0].trim(), smiles: parts[1].trim(), category: "导入分子" }
        : { name: `Imported-${i + 1}`, smiles: parts[0].trim(), category: "导入分子" };
    });
    const res = await molApi.inspectSmilesBatch(reqItems);
    const valid = res.items.filter((x) => x.ok);
    const failed = res.items.length - valid.length;
    if (valid.length > 0) addCustomLibraryItems(valid);
    pushNotification(
      failed > 0 ? "warning" : "success",
      `已解析导入 ${valid.length} 个分子${failed > 0 ? `，跳过 ${failed} 个无效 SMILES` : ""}`
    );
    setShowImport(false);
  };

  const handleExportCsv = () => {
    const target = selectedIds.size > 0 ? filtered.filter((x) => selectedIds.has(x.id)) : filtered;
    const rows = ["Name,Category,Formula,MW_Da,Atoms,Bonds,SMILES"];
    for (const m of target) {
      rows.push(`"${m.name}","${m.category}","${m.formula}",${m.molecular_weight},${m.num_atoms},${m.num_bonds},"${m.smiles}"`);
    }
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "molforge_library_export.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div data-testid="view-library" className="h-full flex flex-col min-h-0 p-4 gap-3">
      {/* Toolbar */}
      <div className="studio-surface p-3 flex flex-wrap items-center justify-between gap-2.5 shrink-0">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索名称、化学式或 SMILES..."
              className="studio-input pl-8 w-[240px]"
            />
          </div>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="studio-input"
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                分类：{c}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={() => {
              if (sortBy === "mw") setSortAsc(!sortAsc);
              else { setSortBy("mw"); setSortAsc(true); }
            }}
            className="studio-btn"
          >
            <ArrowDownUp size={12.5} />
            <span>按分子量</span>
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <button type="button" onClick={() => setShowImport(!showImport)} className="studio-btn">
            <Upload size={12.5} />
            <span>批量导入 SMILES</span>
          </button>
          <button type="button" onClick={handleExportCsv} className="studio-btn">
            <Download size={12.5} />
            <span>导出 CSV ({selectedIds.size || filtered.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setShowCols((s) => ({ ...s, smiles: !s.smiles }))}
            className="studio-btn"
            title="切换 SMILES 列显示"
          >
            <Columns3 size={13} />
          </button>

          <div className="flex items-center p-0.5 rounded-lg" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border-subtle)" }}>
            <button
              type="button"
              onClick={() => setViewMode("table")}
              className="h-6 px-2 rounded cursor-pointer flex items-center"
              style={viewMode === "table" ? { backgroundColor: "var(--accent-primary)", color: "var(--accent-contrast)" } : { color: "var(--text-secondary)" }}
              title="表格视图"
            >
              <List size={13} />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("cards")}
              className="h-6 px-2 rounded cursor-pointer flex items-center"
              style={viewMode === "cards" ? { backgroundColor: "var(--accent-primary)", color: "var(--accent-contrast)" } : { color: "var(--text-secondary)" }}
              title="卡片视图"
            >
              <Grid2x2 size={13} />
            </button>
          </div>
        </div>
      </div>

      {/* Batch Import Panel */}
      {showImport && (
        <div className="studio-surface p-3 space-y-2 shrink-0">
          <div className="text-[12px] font-semibold">批量导入 SMILES（每行格式：名称,SMILES 或直接 SMILES，由后端 RDKit 实算拓扑与 2D 坐标）</div>
          <textarea
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            rows={3}
            className="w-full p-2 rounded-lg mono-num text-[12px]"
            style={{ backgroundColor: "var(--bg-input)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)", userSelect: "text" }}
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowImport(false)} className="studio-btn">取消</button>
            <button type="button" onClick={() => void handleBatchImport()} className="studio-btn studio-btn-primary">
              <Plus size={13} />
              <span>验证并加入分子库</span>
            </button>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 min-h-0 studio-surface overflow-hidden flex flex-col">
        {viewMode === "table" ? (
          <div className="flex-1 studio-scroll">
            <table className="w-full text-left border-collapse text-[12px]">
              <thead className="sticky top-0 z-10" style={{ backgroundColor: "var(--bg-secondary)", borderBottom: "1px solid var(--border-subtle)" }}>
                <tr style={{ color: "var(--text-secondary)" }}>
                  <th className="p-2.5 w-8">
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && selectedIds.size === filtered.length}
                      onChange={(e) =>
                        setSelectedIds(e.target.checked ? new Set(filtered.map((x) => x.id)) : new Set())
                      }
                    />
                  </th>
                  <th className="p-2.5 w-[108px]">2D 结构</th>
                  <th className="p-2.5">名称 / 分类</th>
                  {showCols.formula && <th className="p-2.5">化学式</th>}
                  {showCols.mw && <th className="p-2.5">分子量 (Da)</th>}
                  {showCols.atoms && <th className="p-2.5">原子 / 键</th>}
                  {showCols.smiles && <th className="p-2.5">SMILES</th>}
                  <th className="p-2.5 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const sel = selectedIds.has(item.id);
                  return (
                    <tr
                      key={item.id}
                      className="border-b hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                      style={{ borderColor: "var(--border-subtle)" }}
                    >
                      <td className="p-2.5">
                        <input
                          type="checkbox"
                          checked={sel}
                          onChange={(e) => {
                            const next = new Set(selectedIds);
                            if (e.target.checked) next.add(item.id);
                            else next.delete(item.id);
                            setSelectedIds(next);
                          }}
                        />
                      </td>
                      <td className="p-1.5">
                        <StructureThumbnail2D preview={item.preview_2d} width={96} height={54} />
                      </td>
                      <td className="p-2.5">
                        <div className="font-semibold">{item.name}</div>
                        <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>{item.category}</div>
                      </td>
                      {showCols.formula && <td className="p-2.5 mono-num">{item.formula}</td>}
                      {showCols.mw && <td className="p-2.5 mono-num">{item.molecular_weight.toFixed(2)}</td>}
                      {showCols.atoms && (
                        <td className="p-2.5 mono-num">
                          {item.num_atoms} / {item.num_bonds}
                        </td>
                      )}
                      {showCols.smiles && (
                        <td className="p-2.5 max-w-[260px]">
                          <div className="flex items-center gap-1.5">
                            <span className="mono-num text-[11px] truncate" title={item.smiles} style={{ userSelect: "text" }}>
                              {item.smiles}
                            </span>
                            <button
                              type="button"
                              onClick={() => {
                                void navigator.clipboard.writeText(item.smiles);
                                setCopiedId(item.id);
                                setTimeout(() => setCopiedId(null), 1500);
                              }}
                              className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10 cursor-pointer shrink-0"
                              title="复制 SMILES"
                            >
                              {copiedId === item.id ? <Check size={12} style={{ color: "var(--accent-primary)" }} /> : <Copy size={12} />}
                            </button>
                          </div>
                        </td>
                      )}
                      <td className="p-2.5 text-right">
                        <button
                          type="button"
                          onClick={() => handleLoadItem(item)}
                          className="studio-btn studio-btn-primary !h-7 !px-2.5"
                        >
                          载入工作台
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex-1 studio-scroll p-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 content-start">
            {filtered.map((item) => (
              <div key={item.id} className="studio-inset p-3 flex flex-col justify-between gap-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[12.5px] font-semibold truncate">{item.name}</div>
                    <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>{item.category}</div>
                  </div>
                  <span className="mono-num text-[11px] px-1.5 py-0.5 rounded" style={{ backgroundColor: "var(--accent-soft)", color: "var(--accent-primary)" }}>
                    {item.formula}
                  </span>
                </div>
                <div className="flex justify-center py-1 rounded-md" style={{ backgroundColor: "var(--bg-panel)" }}>
                  <StructureThumbnail2D preview={item.preview_2d} width={180} height={96} />
                </div>
                <div className="flex items-center justify-between text-[11px] mono-num" style={{ color: "var(--text-secondary)" }}>
                  <span>{item.molecular_weight.toFixed(2)} Da</span>
                  <span>{item.num_atoms} 原子</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleLoadItem(item)}
                  className="studio-btn studio-btn-primary w-full"
                >
                  打开至分子编辑器
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
