/* global Buffer, setTimeout, KeyboardEvent */
// 最小探针：悬停热键为何不生效（C6/C7 归因）
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
const app = await electron.launch({ args: [desktopRoot], env: { ...process.env, NODE_ENV: "production" } });
const win = await app.firstWindow();
await win.setViewportSize({ width: 1440, height: 880 });
await win.waitForSelector('[data-testid="title-bar"]', { timeout: 20000 });
await win.waitForFunction(() => document.body.innerText.includes("化学计算内核在线"), null, { timeout: 15000 });
await win.click('[data-testid="nav-editor"]'); await win.waitForSelector('[data-testid="view-editor"]'); await sleep(400); await api("POST", "/api/build/preset", { id: "caffeine" });
await sleep(1000);
let cs = await centers(win);
console.log("centers0=", JSON.stringify(cs[0]), "count=", cs.length);
const hint = await win.evaluate(() => document.body.innerText.slice(0, 0) || [...document.querySelectorAll("div")].map((d) => d.innerText).find((t) => t && t.includes("选择")) || "(no hint)");
console.log("toolhint=", String(hint).slice(0, 80));
await win.mouse.move(cs[0].x, cs[0].y);
await sleep(300);
// 悬停是否命中：看原子 g 是否有 hover 视觉（stroke 变化）或直接用 elementFromPoint
const atPoint = await win.evaluate(([x, y]) => { const el = document.elementFromPoint(x, y); return el ? el.tagName + "." + (el.getAttribute("class") || "") + " r=" + (el.getAttribute("r") || "") : "null"; }, [cs[0].x, cs[0].y]);
console.log("elementFromPoint=", atPoint);
await win.keyboard.press("o");
await sleep(700);
console.log("after real press o:", (await api("GET", "/api/atoms")).atoms[0].symbol);
await win.evaluate(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "o", bubbles: true })));
await sleep(700);
console.log("after synthetic o:", (await api("GET", "/api/atoms")).atoms[0].symbol);
await win.keyboard.press("a"); // atom 工具
await sleep(300);
await win.mouse.move(cs[0].x + 2, cs[0].y + 2);
await sleep(300);
await win.keyboard.press("o");
await sleep(700);
console.log("after atom-tool o:", (await api("GET", "/api/atoms")).atoms[0].symbol);
// F 组归因：空白点命中谁 + Shift 多选测量
await win.keyboard.press("v");
await sleep(300);
cs = await centers(win);
const empty = await win.evaluate(() => { const r = document.querySelector('svg[data-testid="canvas-2d"]').getBoundingClientRect(); return { x: r.x + 25, y: r.y + 25 }; });
console.log("emptyFromPoint=", await win.evaluate(([x, y]) => { const el = document.elementFromPoint(x, y); return el ? el.tagName + " testid=" + (el.getAttribute("data-testid") || "") : "null"; }, [empty.x, empty.y]));
async function meas(n) {
  await win.mouse.click(empty.x, empty.y); await sleep(200);
  await win.keyboard.down("Shift");
  for (let i = 0; i < n; i++) { await win.mouse.click(cs[i].x, cs[i].y); await sleep(200); }
  await win.keyboard.up("Shift"); await sleep(300);
  return win.evaluate(() => { const m = document.body.innerText.match(/(距离|键角|二面角) \([^\n]*/g); return m ? m.join(" | ") : "(无)"; });
}
console.log("meas2=", await meas(2));
console.log("meas3=", await meas(3));
console.log("meas4=", await meas(4));
await app.close();

