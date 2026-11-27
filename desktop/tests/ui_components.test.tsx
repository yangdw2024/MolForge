import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StructureThumbnail2D } from "../src/components/common/StructureThumbnail2D";
import { EnergyLadderChart } from "../src/components/charts/EnergyLadderChart";
import { AnalysisPlotChart } from "../src/components/charts/AnalysisPlotChart";

describe("MolForge Studio Scientific UI Components", () => {
  it("renders StructureThumbnail2D vector bonds cleanly and handles empty state", () => {
    const { container, rerender } = render(<StructureThumbnail2D preview={null} />);
    expect(screen.getByText("无二维结构")).toBeTruthy();

    rerender(
      <StructureThumbnail2D
        preview={{
          atoms: [
            { index: 0, symbol: "C", atomic_num: 6, x2: 0, y2: 0, color: [140, 140, 140] },
            { index: 1, symbol: "O", atomic_num: 8, x2: 1.2, y2: 0, color: [240, 60, 60] },
          ],
          bonds: [{ i: 0, j: 1, order: 2, aromatic: false }],
        }}
      />
    );
    expect(container.querySelectorAll("line").length).toBe(2);
    expect(screen.getByText("O")).toBeTruthy();
  });

  it("renders EnergyLadderChart with real TB values and eV axis", () => {
    render(
      <EnergyLadderChart
        activeName="咖啡因"
        qcParsed={null}
        tbResult={{
          molecule_name: "咖啡因",
          homo_ev: -5.965,
          lumo_ev: -2.05,
          gap_ev: 3.915,
          references: [{ name: "PM6 (经典给体)", homo_ev: -5.5, lumo_ev: -3.61, color: "#60A5FA" }],
        }}
      />
    );
    expect(screen.getByText(/HOMO \/ LUMO Energy Ladder/)).toBeTruthy();
    expect(screen.getByText(/H -5\.96/)).toBeTruthy();
    expect(screen.getByText(/Eg=3.92 eV/)).toBeTruthy();
  });

  it("renders AnalysisPlotChart empty state and XY curve plot", () => {
    const { rerender } = render(<AnalysisPlotChart result={null} />);
    expect(screen.getByText("尚未运行分析项")).toBeTruthy();

    rerender(
      <AnalysisPlotChart
        result={{
          analysis_id: "WFN-02",
          title: "HOMO/LUMO 轨道能量序列",
          status: "completed",
          summary: "已计算前线轨道",
          metrics: { homo_ev: -5.96 },
          plot_x: [1, 2, 3],
          plot_y: [-6.4, -5.96, -2.05],
          x_label: "Orbital Index",
          y_label: "Energy (eV)",
        }}
      />
    );
    expect(screen.getByText("WFN-02")).toBeTruthy();
    expect(screen.getByText("Energy (eV)")).toBeTruthy();
  });
});
