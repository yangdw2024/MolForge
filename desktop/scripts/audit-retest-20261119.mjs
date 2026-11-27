/* global Buffer, setTimeout */
// 聚焦复测：F 四原子二面角 / I1 AI上下文(经UI加载) / H1 并五苯404提示
import { _electron as electron } from "playwright";
import fs from "node:fs";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(__dirname, "..");
const outDir = "E:\\YDW\\Trae_Chemdraw\\docs\\desktop\\audit_20261119\\evidence\\ui";
const results = [];
const record = (id, name, pass, detail) => { results.push({ id, name, pass, detail }); console.log(`[RETEST] ${pass ? "PASS" : "FAIL"} ${id} ${name} :: ${detail}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function api(method, p, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req = http.request({ host: "127.0.0.1", port: 18765, path: p, method, headers: data ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } : {} }, (res) => { let b = ""; res.on("data", (c) => (b += c)); res.on("end", () => { try { resolve({ status: res.statusCode, ...JSON.parse(b) }); } catch { resolve({ status: res.statusCode, raw: b }); } }); });
    req.on("error", reject); if (data) req.write(data); req.end();
  });
}
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
    await sleep(400);
    await win.keyboard.press("v");
    await sleep(200);

    // 经 UI 生成咖啡因（store 同步）
    await win.locator('input[placeholder="输入 SMILES 生成分子..."]').fill("Cn1cnc2c1c(=O)n(C)c(=O)n2C");
    await win.locator("button", { hasText: "生成" }).first().click();
    await sleep(1500);

    // I1 复测：AI 上下文徽章
    await win.locator('button:has(span:text-is("AI"))').first().click();
    await sleep(500);
    const aiContext = await win.evaluate(() => { const t = document.body.innerText; const i = t.indexOf("上下文:"); return i >= 0 ? t.slice(i, i + 120).replace(/\n/g, " | ") : "(无)"; });
    record("I1r", "AI上下文徽章(经UI加载)", aiContext.includes("C8H10N4O2") && aiContext.includes("24 原子"), aiContext);
    await win.screenshot({ path: path.join(outDir, "audit_I1_ai_context_retest.png") });
    await win.locator('button:has(span:text-is("AI"))').first().click();
    await sleep(200);

    // F 复测：选 4 个空间分散原子
    const centers = await win.evaluate(() => {
      const svg = document.querySelector('svg[data-testid="canvas-2d"]');
      const gs = [...svg.querySelectorAll("g[transform]")];
      const out = [];
      for (const g of gs) { const c = g.querySelector('circle[r="10"]'); if (!c) continue; const r = c.getBoundingClientRect(); out.push({ x: r.x + r.width / 2, y: r.y + r.height / 2 }); }
      return out;
    });
    // 选分散的4个：0, 6, 12, 18
    const picks = [0, 6, 12, 18].filter((i) => i < centers.length);
    // 空白点：取距所有原子最远的画布角落
    const emptyPt = await win.evaluate((cs) => {
      const svg = document.querySelector('svg[data-testid="canvas-2d"]');
      const r = svg.getBoundingClientRect();
      const corners = [{ x: r.x + 20, y: r.y + 20 }, { x: r.right - 20, y: r.y + 20 }, { x: r.x + 20, y: r.bottom - 20 }, { x: r.right - 20, y: r.bottom - 20 }];
      let best = corners[0], bestD = -1;
      for (const c of corners) { const d = Math.min(...cs.map((a) => Math.hypot(a.x - c.x, a.y - c.y))); if (d > bestD) { bestD = d; best = c; } }
      return best;
    }, centers);
    await win.mouse.click(emptyPt.x, emptyPt.y);
    await sleep(250);
    await win.keyboard.down("Shift");
    for (const i of picks) { await win.mouse.click(centers[i].x, centers[i].y); await sleep(250); }
    await win.keyboard.up("Shift");
    await sleep(400);
    const m4 = await win.evaluate(() => { const t = document.body.innerText; const m = t.match(/(距离|键角|二面角) \([^\n]*/g); return m ? m.join(" | ") : "(无测量文本)"; });
    await win.screenshot({ path: path.join(outDir, "audit_F4_dihedral_retest.png") });
    record("F4r", "4原子二面角HUD", m4.includes("二面角"), m4);
    record("F4r-mock", "二面角为硬编码Mock", m4.includes("0.00° (共平面)"), `${m4} → EditorView.tsx:152 硬编码"0.00° (共平面)"，无论选哪4个原子都显示共平面`);
    // 3原子复测
    await win.mouse.click(emptyPt.x, emptyPt.y); await sleep(250);
    await win.keyboard.down("Shift");
    for (const i of [0, 6, 12]) { await win.mouse.click(centers[i].x, centers[i].y); await sleep(250); }
    await win.keyboard.up("Shift"); await sleep(400);
    const m3 = await win.evaluate(() => { const t = document.body.innerText; const m = t.match(/(距离|键角|二面角) \([^\n]*/g); return m ? m.join(" | ") : "(无)"; });
    await win.screenshot({ path: path.join(outDir, "audit_F3_angle_retest.png") });
    record("F3r", "3原子键角HUD", m3.includes("键角") && /\d+\.\d°/.test(m3), m3);

    // H1 复测：并五苯 404 提示
    await win.locator('button:has(span:text-is("砌块库"))').first().click();
    await sleep(400);
    await win.evaluate(() => { const wins = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='展开']")); const f = wins.find((w) => w.innerText.includes("砌块库")); f?.querySelector("button[title='展开']")?.click(); });
    await sleep(300);
    const before = await api("GET", "/api/document");
    await win.locator("div.cursor-pointer", { hasText: "并五苯" }).first().click();
    await sleep(1200);
    const after = await api("GET", "/api/document");
    const toastText = await win.evaluate(() => { const t = document.body.innerText; const i = t.indexOf("pentacene"); const j = t.indexOf("未找到"); const k = t.indexOf("插入片段"); return { pentacene: i >= 0 ? t.slice(i - 40, i + 80) : null, notfound: j >= 0 ? t.slice(j - 40, j + 80) : null, insert: k >= 0 ? t.slice(k - 20, k + 100) : null }; });
    await win.screenshot({ path: path.join(outDir, "audit_H1_pentacene_retest.png") });
    record("H1r", "并五苯插入(后端缺项)", after.num_atoms > before.num_atoms, `atoms ${before.num_atoms}→${after.num_atoms}; toast=${JSON.stringify(toastText)}`);
    // 直接 API 验证 pentacene/benzene 404
    const rp = await api("POST", "/api/edit/insert_fragment", { fragment_id: "pentacene" });
    const rb = await api("POST", "/api/edit/insert_fragment", { fragment_id: "benzene" });
    record("H1r-api", "pentacene/benzene片段404", rp.status === 404 && rb.status === 404, `pentacene HTTP=${rp.status} error=${rp.error}; benzene HTTP=${rb.status} error=${rb.error}`);
    fs.writeFileSync(path.join(outDir, "retest_results.json"), JSON.stringify({ results, rp, rb }, null, 2), "utf8");
  } finally { await app.close(); }
}
run().catch((e) => { console.error("[RETEST] FATAL:", e.message); fs.writeFileSync(path.join(outDir, "retest_results.json"), JSON.stringify(results, null, 2), "utf8"); process.exit(1); });