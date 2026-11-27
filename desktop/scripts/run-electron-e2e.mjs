import { _electron as electron } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(__dirname, "..");
const outDir = path.resolve(desktopRoot, "test-artifacts");
fs.mkdirSync(outDir, { recursive: true });

function assert(cond, msg) {
  if (!cond) throw new Error(`Assertion failed: ${msg}`);
}

async function run() {
  const packaged = process.argv.includes("--packaged");
  const launchOpts = packaged
    ? {
        executablePath: path.resolve(desktopRoot, "release", "win-unpacked", "MolForge Studio.exe"),
      }
    : {
        args: [desktopRoot],
        env: {
          ...process.env,
          NODE_ENV: "production",
        },
      };
  console.log(
    packaged ? "[E2E] Launching PACKAGED MolForge Studio.exe:" : "[E2E] Launching built Electron desktop app:",
    packaged ? launchOpts.executablePath : desktopRoot
  );
  const app = await electron.launch(launchOpts);

  const pageErrors = [];
  try {
    const win = await app.firstWindow();
    win.on("pageerror", (err) => {
      console.error("[Renderer PageError]", err.message);
      pageErrors.push(err.message);
    });
    win.on("console", (msg) => {
      if (msg.type() === "error") console.error("[Renderer ConsoleError]", msg.text());
    });

    await win.setViewportSize({ width: 1440, height: 880 });
    await win.waitForSelector('[data-testid="title-bar"]', { timeout: 20000 });
    await win.waitForSelector('[data-testid="view-overview"]', { timeout: 20000 });

    // 1. Security Isolation Verification inside Renderer
    const secCheck = await win.evaluate(() => ({
      hasDesktopBridge: Boolean(window.molforgeDesktop?.isElectron),
      hasNodeRequire: typeof window.require !== "undefined",
      hasNodeProcess: typeof window.process !== "undefined",
      theme: document.documentElement.getAttribute("data-theme"),
    }));
    assert(secCheck.hasDesktopBridge, "window.molforgeDesktop must be exposed via contextBridge");
    assert(!secCheck.hasNodeRequire, "nodeIntegration must be false (window.require undefined)");
    assert(!secCheck.hasNodeProcess, "sandbox must isolate window.process");

    // Wait for bridge connection to settle
    await win.waitForFunction(
      () => document.body.innerText.includes("化学计算内核在线"),
      null,
      { timeout: 15000 }
    );
    await win.waitForTimeout(400);
    await win.screenshot({ path: path.join(outDir, "scene_01_overview_obsidian.png") });
    console.log("[E2E] Scene 01 Overview (Obsidian) captured");

    // 2. Navigate to Molecule Library & load a molecule
    await win.click('[data-testid="nav-library"]');
    await win.waitForSelector('[data-testid="view-library"]');
    await win.waitForTimeout(350);
    await win.screenshot({ path: path.join(outDir, "scene_02_library_obsidian.png") });
    console.log("[E2E] Scene 02 Library captured");

    // Load Pentacene or second preset row into Editor
    const loadButtons = await win.locator('[data-testid="view-library"] button:has-text("载入工作台")').all();
    assert(loadButtons.length >= 4, "Library presets must render multiple entries");
    await loadButtons[0].click();
    await win.waitForSelector('[data-testid="view-editor"]');
    await win.waitForTimeout(400);

    // 3. Open 118-element Periodic Table modal & pick Platinum (78 Pt)
    await win.click('[data-testid="open-pt-modal-btn"]');
    await win.waitForSelector('[data-testid="periodic-table-modal"]');
    await win.fill('[data-testid="periodic-table-modal"] input', "Pt");
    await win.waitForTimeout(200);
    await win.screenshot({ path: path.join(outDir, "scene_03_periodic_table_118.png") });
    await win.click('[data-testid="periodic-table-modal"] button[title*="Z=78"]');
    const activeElText = await win.textContent('[data-testid="active-element-badge"]');
    assert(activeElText && activeElText.includes("Pt"), `Expected active element Pt, got ${activeElText}`);
    await win.screenshot({ path: path.join(outDir, "scene_04_editor_obsidian.png") });
    console.log("[E2E] Scene 03/04 Periodic Table + Editor (Obsidian) captured");

    // 3b. Switch to 2D+3D Split & Open OSC Fragments + AI Copilot HUD layers
    await win.click('button:has-text("2D+3D")');
    await win.click('button:has-text("砌块库")');
    await win.click('button:has-text("AI")');
    await win.waitForTimeout(350);
    await win.screenshot({ path: path.join(outDir, "scene_04b_split_hud_layers.png") });
    await win.click('button:has-text("砌块库")');
    await win.click('button:has-text("AI")');
    console.log("[E2E] Scene 04b Split View + Floating HUD Layers captured");

    // 4. Switch to Analysis Workbench, run Tight-Binding + CORE-01 + Real Multiwfn 3.8
    await win.click('[data-testid="nav-analysis"]');
    await win.waitForSelector('[data-testid="view-analysis"]');
    await win.click('[data-testid="run-tb-btn"]');
    await win.waitForFunction(
      () => document.body.innerText.includes("TB HOMO"),
      null,
      { timeout: 10000 }
    );
    await win.click('[data-testid="run-selected-analysis-btn"]');
    await win.click('[data-testid="engine-tab-multiwfn"]');
    await win.click('[data-testid="run-multiwfn-doc-btn"]');
    await win.waitForFunction(
      () => document.body.innerText.includes("Multiwfn 实算完成"),
      null,
      { timeout: 15000 }
    );
    await win.waitForTimeout(350);
    await win.screenshot({ path: path.join(outDir, "scene_05_analysis_obsidian.png") });
    console.log("[E2E] Scene 05 Analysis Workbench + Multiwfn real execution captured");

    // 4b. Navigate to MolForge Hub, plan & execute workflow with provenance, verify SKILL.md import
    await win.click('[data-testid="nav-hub"]');
    await win.waitForSelector('[data-testid="view-hub"]');
    await win.click('[data-testid="hub-ai-plan-btn"]');
    await win.waitForSelector('[data-testid="hub-ai-proposal"]');
    await win.click('[data-testid="hub-run-proposal-btn"]');
    await win.waitForSelector('[data-testid="hub-active-run"]');
    await win.waitForFunction(
      () => document.body.innerText.includes("Provenance Run:"),
      null,
      { timeout: 10000 }
    );
    await win.screenshot({ path: path.join(outDir, "scene_05b_hub_obsidian.png") });
    console.log("[E2E] Scene 05b MolForge Hub + AI Workflow Provenance captured");

    // 5. Switch to Jobs & submit real Tight-Binding background job
    await win.click('[data-testid="nav-jobs"]');
    await win.waitForSelector('[data-testid="view-jobs"]');
    await win.click('[data-testid="submit-tb-job-btn"]');
    await win.waitForFunction(
      () => document.body.innerText.includes("Completed"),
      null,
      { timeout: 10000 }
    );
    await win.screenshot({ path: path.join(outDir, "scene_06_jobs_obsidian.png") });
    console.log("[E2E] Scene 06 Jobs Center captured");

    // 6. Reports View
    await win.click('[data-testid="nav-reports"]');
    await win.waitForSelector('[data-testid="view-reports"]');
    await win.waitForTimeout(250);
    await win.screenshot({ path: path.join(outDir, "scene_07_reports_obsidian.png") });

    // 7. Settings + External Engines Probe Verification + Switch to Arctic Laboratory (Light Theme)
    await win.click('[data-testid="nav-settings"]');
    await win.waitForSelector('[data-testid="view-settings"]');
    await win.waitForSelector('[data-testid="engines-registry-section"]');
    const enginesText = await win.textContent('[data-testid="engines-registry-section"]');
    assert(enginesText && enginesText.includes("已就绪"), "External scientific engines should probe as ready");
    const currentTheme = await win.evaluate(() => document.documentElement.getAttribute("data-theme"));
    if (currentTheme !== "arctic") {
      await win.click('[data-testid="theme-toggle-btn"]');
    }
    const arcticTheme = await win.evaluate(() => document.documentElement.getAttribute("data-theme"));
    assert(arcticTheme === "arctic", `Expected arctic theme, got ${arcticTheme}`);
    await win.waitForTimeout(300);
    await win.screenshot({ path: path.join(outDir, "scene_08_settings_arctic.png") });

    // 8. Editor under Arctic Light Theme + Compact 1280x800 Viewport + Command Palette
    await win.setViewportSize({ width: 1280, height: 800 });
    await win.click('[data-testid="nav-editor"]');
    await win.waitForSelector('[data-testid="view-editor"]');
    await win.waitForTimeout(400);
    await win.screenshot({ path: path.join(outDir, "scene_09_editor_arctic_1280x800.png") });

    await win.click('[data-testid="command-palette-trigger"]');
    await win.waitForSelector('[data-testid="command-palette"]');
    await win.screenshot({ path: path.join(outDir, "scene_10_command_palette.png") });
    await win.keyboard.press("Escape");

    // Reset back to obsidian theme for clean default next boot
    const endTheme = await win.evaluate(() => document.documentElement.getAttribute("data-theme"));
    if (endTheme !== "obsidian") {
      await win.click('[data-testid="theme-toggle-btn"]');
    }

    assert(pageErrors.length === 0, `Uncaught pageErrors: ${pageErrors.join("; ")}`);
    console.log("[E2E] ALL 10 SCENES & FLOWS PASSED WITH ZERO ERRORS!");
  } finally {
    await app.close();
  }
}

run().catch((err) => {
  console.error("[E2E] FAILED:", err);
  process.exit(1);
});
