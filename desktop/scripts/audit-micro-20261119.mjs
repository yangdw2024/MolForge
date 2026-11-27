/* global setTimeout */
// 微补证：3原子键角干净截图 + 通知抽屉中的并五苯失败记录
import { _electron as electron } from "playwright";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(__dirname, "..");
const outDir = "E:\\YDW\\Trae_Chemdraw\\docs\\desktop\\audit_20261119\\evidence\\ui";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function run() {
  const app = await electron.launch({ args: [desktopRoot], env: { ...process.env, NODE_ENV: "production" } });
  try {
    const win = await app.firstWindow();
    await win.setViewportSize({ width: 1440, height: 880 });
    await win.waitForSelector('[data-testid="title-bar"]', { timeout: 20000 });
    await win.waitForFunction(() => document.body.innerText.includes("化学计算内核在线"), null, { timeout: 15000 });
    await sleep(400);
    await win.click('[data-testid="nav-editor"]');
    await win.waitForSelector('[data-testid="view-editor"]');
    await win.locator('button:text-is("2D")').first().click().catch(() => {});
    await sleep(300);
    await win.keyboard.press("v");
    await win.locator('input[placeholder="输入 SMILES 生成分子..."]').fill("Cn1cnc2c1c(=O)n(C)c(=O)n2C");
    await win.locator("button", { hasText: "生成" }).first().click();
    await sleep(1500);
    const centers = await win.evaluate(() => {
      const svg = document.querySelector('svg[data-testid="canvas-2d"]');
      return [...svg.querySelectorAll("g[transform]")].map((g) => { const c = g.querySelector('circle[r="10"]'); if (!c) return null; const r = c.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; }).filter(Boolean);
    });
    // 3原子：0,6,12
    await win.keyboard.down("Shift");
    for (const i of [0, 6, 12]) { await win.mouse.click(centers[i].x, centers[i].y); await sleep(250); }
    await win.keyboard.up("Shift");
    await sleep(400);
    const m3 = await win.evaluate(() => (document.body.innerText.match(/(距离|键角|二面角) \([^\n]*/g) || []).join(" | "));
    await win.screenshot({ path: path.join(outDir, "audit_F3_angle_clean.png") });
    console.log("[MICRO] 3原子测量:", m3);
    // 加选第4个 → 二面角
    await win.keyboard.down("Shift");
    await win.mouse.click(centers[18].x, centers[18].y);
    await win.keyboard.up("Shift");
    await sleep(400);
    const m4 = await win.evaluate(() => (document.body.innerText.match(/(距离|键角|二面角) \([^\n]*/g) || []).join(" | "));
    await win.screenshot({ path: path.join(outDir, "audit_F4_dihedral_clean.png") });
    console.log("[MICRO] 4原子测量:", m4);
    // 并五苯失败 → 通知抽屉
    await win.locator('button:has(span:text-is("砌块库"))').first().click();
    await sleep(400);
    await win.evaluate(() => { const w = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='展开']")).find((x) => x.innerText.includes("砌块库")); w?.querySelector("button[title='展开']")?.click(); });
    await sleep(300);
    await win.locator("div.cursor-pointer", { hasText: "并五苯" }).first().click();
    await sleep(1000);
    // 打开通知抽屉（状态栏铃铛）
    const bell = win.locator('button[title="查看事件与通知日志"]');
    await bell.click();
    await sleep(400);
    const drawerText = await win.evaluate(() => { const t = document.body.innerText; const i = t.indexOf("系统事件与诊断通知"); return i >= 0 ? t.slice(i, i + 500).replace(/\n/g, " | ") : "(抽屉未打开)"; });
    await win.screenshot({ path: path.join(outDir, "audit_H1_notification_drawer.png") });
    console.log("[MICRO] 通知抽屉:", drawerText);
    fs.writeFileSync(path.join(outDir, "micro_results.json"), JSON.stringify({ m3, m4, drawerText }, null, 2), "utf8");
  } finally { await app.close(); }
}
run().catch((e) => { console.error("[MICRO] FATAL:", e.message); process.exit(1); });