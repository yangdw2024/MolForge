/* global Buffer, setTimeout */
// 二分归因：C6 悬停热键在 E2E 前序状态下为何失效
import { _electron as electron } from "playwright";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(__dirname, "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function api(method, p, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req = http.request({ host: "127.0.0.1", port: 18765, path: p, method, headers: data ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } : {} }, (res) => { let b = ""; res.on("data", (c) => (b += c)); res.on("end", () => { try { resolve(JSON.parse(b)); } catch { resolve({ raw: b }); } }); });
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}
async function centers(win) {
  return win.evaluate(() => {
    const svg = document.querySelector('svg[data-testid="canvas-2d"]');
    if (!svg) return [];
    return [...svg.querySelectorAll("g[transform]")].map((g) => { const c = g.querySelector('circle[r="10"]'); if (!c) return null; const r = c.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; }).filter(Boolean);
  });
}
async function reset(win) {
  await api("POST", "/api/build/preset", { id: "caffeine" });
  await win.waitForFunction(() => document.querySelectorAll('svg[data-testid="canvas-2d"] circle[r="10"]').length === 24, null, { timeout: 5000 });
  await sleep(200);
}
async function hoverPress(win, key) {
  const cs = await centers(win);
  await win.mouse.move(cs[0].x - 60, cs[0].y - 60);
  await sleep(150);
  await win.mouse.move(cs[0].x, cs[0].y);
  await sleep(250);
  await win.keyboard.press(key);
  await sleep(600);
  return (await api("GET", "/api/atoms")).atoms[0].symbol;
}
const app = await electron.launch({ args: [desktopRoot], env: { ...process.env, NODE_ENV: "production" } });
const win = await app.firstWindow();
win.on("console", (m) => { if (m.text().includes("[HK]")) console.log("RENDERER:", m.text()); });
await win.setViewportSize({ width: 1440, height: 880 });
await win.waitForSelector('[data-testid="title-bar"]', { timeout: 20000 });
await win.waitForFunction(() => document.body.innerText.includes("化学计算内核在线"), null, { timeout: 15000 });
await win.click('[data-testid="nav-editor"]');
await win.waitForSelector('[data-testid="view-editor"]');
await sleep(400);
await reset(win);
console.log("V0 select工具 直接悬停o =>", await hoverPress(win, "o"));
await reset(win);
await win.locator('[data-testid="chemical-tool-rail"] button[title^="原子工具"]').click();
await sleep(250);
await win.locator('[data-testid="chemical-tool-rail"] button[title*="Z=7"]').first().click();
await sleep(250);
console.log("V1 atom工具 悬停o =>", await hoverPress(win, "o"));
await reset(win);
const cs = await centers(win);
await win.mouse.click(cs[0].x, cs[0].y, { button: "right" });
await sleep(300);
await win.keyboard.press("Escape");
await sleep(200);
console.log("V2 atom工具+右键Escape 悬停o =>", await hoverPress(win, "o"));
await reset(win);
await win.mouse.click(cs[1].x, cs[1].y, { button: "right" });
await sleep(300);
const del = win.locator("button", { hasText: "删除此原子" });
if (await del.isVisible().catch(() => false)) { await del.click(); await sleep(400); }
await win.keyboard.press("Escape");
await sleep(200);
await reset(win);
console.log("V3 再+删除原子 悬停o =>", await hoverPress(win, "o"));
await app.close();