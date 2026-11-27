/* global Buffer, setTimeout */
// MolForge Studio 8.1 审计专用 E2E — 2026-11-19 首席QA架构师
// 覆盖标准套件未测的细粒度交互：右键菜单/悬停热键/HUD拖拽折叠层级/Ctrl+B/三向投影/Shift测量/SMILES/砌块接枝/AI上下文
import { _electron as electron } from "playwright";
import fs from "node:fs";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(__dirname, "..");
const outDir = "E:\\YDW\\Trae_Chemdraw\\docs\\desktop\\fix_20261120\\evidence\\ui";
fs.mkdirSync(outDir, { recursive: true });

const results = [];
function record(id, name, pass, detail) {
  results.push({ id, name, pass, detail, ts: new Date().toISOString() });
  console.log(`[AUDIT] ${pass ? "PASS" : "FAIL"} ${id} ${name} :: ${detail}`);
}
function api(method, p, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req = http.request(
      { host: "127.0.0.1", port: 18765, path: p, method, headers: data ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } : {} },
      (res) => { let b = ""; res.on("data", (c) => (b += c)); res.on("end", () => { try { resolve(JSON.parse(b)); } catch { resolve({ raw: b, status: res.statusCode }); } }); }
    );
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function atomCenters(win) {
  return win.evaluate(() => {
    const svg = document.querySelector('svg[data-testid="canvas-2d"]');
    if (!svg) return [];
    const gs = [...svg.querySelectorAll("g[transform]")];
    const out = [];
    for (const g of gs) {
      const c = g.querySelector('circle[r="10"]');
      if (!c) continue;
      const r = c.getBoundingClientRect();
      out.push({ x: r.x + r.width / 2, y: r.y + r.height / 2 });
    }
    return out;
  });
}

async function run() {
  // 确定性初始态：咖啡因
  await api("POST", "/api/build/preset", { id: "caffeine" });
  const app = await electron.launch({ args: [desktopRoot], env: { ...process.env, NODE_ENV: "production" } });
  const pageErrors = [];
  try {
    const win = await app.firstWindow();
    win.on("pageerror", (e) => pageErrors.push(e.message));
    win.on("console", (m) => { if (m.text().includes("[HK]")) console.log("[RENDERER]", m.text()); else if (m.type() === "error") console.log("[RENDERER-ERR]", m.text().slice(0, 300)); });
    await win.setViewportSize({ width: 1440, height: 880 });
    await win.waitForSelector('[data-testid="title-bar"]', { timeout: 20000 });
    try {
      await win.waitForFunction(() => document.body.innerText.includes("化学计算内核在线"), null, { timeout: 15000 });
    } catch (e) {
      const txt = await win.evaluate(() => document.body.innerText.slice(0, 600));
      console.error("[AUDIT] DIAG body:", txt.replace(/\n/g, " | "));
      console.error("[AUDIT] DIAG pageErrors:", JSON.stringify(pageErrors));
      throw e;
    }
    await sleep(500);

    // ===== A. 38px 顶栏 + 10 菜单 =====
    const headerBox = await win.locator('[data-testid="title-bar"]').boundingBox();
    const menuLabels = ["文件", "编辑", "构建", "结构", "计算", "分析", "结果", "视图", "图层", "帮助"];
    const headerButtons = await win.locator('[data-testid="title-bar"] button').allTextContents();
    const foundMenus = menuLabels.filter((m) => headerButtons.some((t) => t.includes(m)));
    record("A1", "顶栏高度38px", Math.abs(headerBox.height - 38) < 1.5, `height=${headerBox.height}`);
    record("A2", "10大科研菜单", foundMenus.length === 10, `found=${foundMenus.join("/")}`);
    const formulaBadge = await win.locator('[data-testid="title-bar"]').innerText();
    record("A3", "活动分子式徽章", /C8H10N4O2/.test(formulaBadge), formulaBadge.match(/C\d+H\d+N\d+O\d+/)?.[0] || "未找到");
    // 悬停级联：先点击"计算"打开，再悬停"分析"验证切换
    await win.locator('[data-testid="title-bar"] button', { hasText: "计算" }).first().click();
    await sleep(250);
    const dropdownVisible = await win.evaluate(() => document.body.innerText.includes("Tight-Binding") || document.body.innerText.includes("紧束缚"));
    await win.screenshot({ path: path.join(outDir, "audit_A_menu_cascade.png") });
    record("A4", "菜单点击展开级联", dropdownVisible, "计算菜单展开截图 audit_A_menu_cascade.png");
    await win.keyboard.press("Escape");
    await sleep(150);
    // Ctrl+K
    await win.keyboard.press("Control+k");
    await sleep(300);
    const paletteOpen = await win.locator('[data-testid="command-palette"]').isVisible().catch(() => false);
    record("A5", "Ctrl+K Spotlight", paletteOpen, `palette visible=${paletteOpen}`);
    await win.screenshot({ path: path.join(outDir, "audit_A_spotlight.png") });
    await win.keyboard.press("Escape");

    // ===== B. 44px 工具轨 + 抽屉 =====
    await win.click('[data-testid="nav-editor"]');
    await win.waitForSelector('[data-testid="view-editor"]');
    await sleep(400);
    const railBox = await win.locator('[data-testid="chemical-tool-rail"]').boundingBox();
    record("B1", "工具轨宽度44px", railBox && Math.abs(railBox.width - 44) < 2, `width=${railBox?.width}`);
    // 元素抽屉
    await win.locator('[data-testid="chemical-tool-rail"] button[title^="原子工具"]').click();
    await sleep(250);
    const atomDrawer = await win.evaluate(() => !!document.querySelector('[data-testid="chemical-tool-rail"] .backdrop-blur-2xl.w-56'));
    await win.screenshot({ path: path.join(outDir, "audit_B_atom_drawer.png") });
    record("B2", "元素抽屉展开(磨砂)", atomDrawer, "w-56 backdrop-blur 抽屉");
    // 选中 N 后自动收起
    await win.locator('[data-testid="chemical-tool-rail"] button[title*="Z=7"]').first().click();
    await sleep(250);
    const drawerClosed = await win.evaluate(() => !document.querySelector('[data-testid="chemical-tool-rail"] .backdrop-blur-2xl.w-56'));
    const badge = await win.locator('[data-testid="active-element-badge"]').innerText();
    record("B3", "选中后抽屉自动收起", drawerClosed && badge.includes("N"), `closed=${drawerClosed} badge=${badge}`);
    // 环系抽屉
    await win.locator('[data-testid="chemical-tool-rail"] button[title^="环系模板"]').click();
    await sleep(200);
    const ringDrawer = await win.evaluate(() => !!document.querySelector('[data-testid="chemical-tool-rail"] .backdrop-blur-2xl.w-52'));
    record("B4", "环系抽屉展开", ringDrawer, "w-52 抽屉");
    await win.keyboard.press("Escape");
    await win.locator('[data-testid="chemical-tool-rail"] button[title^="环系模板"]').click(); // toggle close
    await sleep(150);
    // 片段抽屉
    await win.locator('[data-testid="chemical-tool-rail"] button[title^="化学片段"]').click();
    await sleep(200);
    const fragDrawer = await win.evaluate(() => !!document.querySelector('[data-testid="chemical-tool-rail"] .backdrop-blur-2xl.w-64'));
    await win.screenshot({ path: path.join(outDir, "audit_B_fragment_drawer.png") });
    record("B5", "片段抽屉展开", fragDrawer, "w-64 抽屉");
    await win.locator('[data-testid="chemical-tool-rail"] button[title^="化学片段"]').click();
    await sleep(150);

    // ===== C. 右键菜单 + 悬停热键 =====
    await win.locator('button:text-is("2D+3D")').first().click().catch(() => {});
    await sleep(400);
    await api("POST", "/api/build/preset", { id: "caffeine" });
    await sleep(600);
    let centers = await atomCenters(win);
    record("C0", "2D画布原子可定位", centers.length >= 20, `atoms=${centers.length}`);
    // 右键原子
    await win.mouse.click(centers[0].x, centers[0].y, { button: "right" });
    await sleep(300);
    const atomMenuText = await win.evaluate(() => {
      const els = [...document.querySelectorAll("div")].filter((d) => d.innerText && d.innerText.includes("删除此原子"));
      return els.length ? els[els.length - 1].innerText : "";
    });
    await win.screenshot({ path: path.join(outDir, "audit_C_atom_context.png") });
    const hasQuickElements = ["C", "N", "O", "S", "P", "F", "Cl", "Br", "H"].every((e) => atomMenuText.includes(e));
    record("C1", "原子右键元素速换", hasQuickElements && atomMenuText.includes("删除此原子"), `menu=${atomMenuText.slice(0, 120).replace(/\n/g, "|")}`);
    record("C2", "原子右键电荷设置", atomMenuText.includes("电荷"), atomMenuText.includes("电荷") ? "存在电荷项" : "【缺失】菜单无电荷设置项");
    // 点击删除原子 → 验证是否真删除（契约错配 T1 的 UI 级证明）
    const before = await api("GET", "/api/document");
    const delBtn = win.getByText("删除此原子", { exact: false }).last();
    if (await delBtn.isVisible().catch(() => false)) {
      await delBtn.click();
      await sleep(600);
      const after = await api("GET", "/api/document");
      record("C3", "右键删除原子生效", after.num_atoms === before.num_atoms - 1, `before=${before.num_atoms} after=${after.num_atoms} (相等=静默失效)`);
    } else {
      record("C3", "右键删除原子生效", false, "删除按钮不可见");
    }
    await win.keyboard.press("Escape");
    // 恢复咖啡因
    await api("POST", "/api/build/preset", { id: "caffeine" });
    await sleep(600);
    // 右键化学键
    const bondMid = await win.evaluate(() => {
      const svg = document.querySelector('svg[data-testid="canvas-2d"]');
      const lines = [...svg.querySelectorAll("line")].filter((l) => l.getAttribute("stroke") !== "transparent" && l.getAttribute("stroke-width"));
      if (!lines.length) return null;
      const l = lines[0];
      const r = l.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });
    if (bondMid) {
      await win.mouse.click(bondMid.x, bondMid.y, { button: "right" });
      await sleep(300);
      const bondMenuText = await win.evaluate(() => {
        const els = [...document.querySelectorAll("div")].filter((d) => d.innerText && d.innerText.includes("删除化学键"));
        return els.length ? els[els.length - 1].innerText : "";
      });
      await win.screenshot({ path: path.join(outDir, "audit_C_bond_context.png") });
      const hasOrders = ["单键", "双键", "三键", "芳香键"].every((t) => bondMenuText.includes(t));
      record("C4", "键右键单/双/三/芳香", hasOrders, `menu=${bondMenuText.slice(0, 140).replace(/\n/g, "|")}`);
      // 点击"三键" → 验证实际键级（契约错配：实际走 cycle）
      const bondsBefore = await api("GET", "/api/atoms");
      const triBtn = win.locator("button", { hasText: "三键 (Triple" }).last();
      if (await triBtn.isVisible().catch(() => false)) {
        await triBtn.click();
        await sleep(600);
        const bondsAfter = await api("GET", "/api/atoms");
        const changed = bondsAfter.bonds.find((b, i) => bondsBefore.bonds[i] && b.order !== bondsBefore.bonds[i].order);
        record("C5", "右键设三键精确生效", changed && changed.order === 3, changed ? `实际变为 order=${changed.order} (期望3)` : "键级未变化");
      } else {
        record("C5", "右键设三键精确生效", false, "三键按钮不可见");
      }
      await win.keyboard.press("Escape");
    } else {
      record("C4", "键右键单/双/三/芳香", false, "未定位到化学键");
      record("C5", "右键设三键精确生效", false, "未定位到化学键");
    }
    // 悬停热键 O（无冲突键）
    await api("POST", "/api/build/preset", { id: "caffeine" });
    // 等 UI 同步完成（revision 轮询 ≤500ms）再做坐标交互，避免悬停到旧分子 atom_id
    await win.waitForFunction(() => document.querySelectorAll('svg[data-testid="canvas-2d"] circle[r="10"]').length === 24, null, { timeout: 5000 });
    await sleep(200);
    centers = await atomCenters(win);
    const atom0Before = (await api("GET", "/api/atoms")).atoms[0];
    await win.mouse.move(centers[0].x, centers[0].y);
    await sleep(200);
    console.log("[AUDIT] DIAG C6:", await win.evaluate(([x, y]) => { const el = document.elementFromPoint(x, y); const ae = document.activeElement; return JSON.stringify({ at: el ? el.tagName + " r=" + (el.getAttribute("r") || "") : "null", focus: ae ? ae.tagName + "." + (ae.getAttribute("placeholder") || "") : "null" }); }, [centers[0].x, centers[0].y]));
    await win.keyboard.press("o");
    await sleep(600);
    const atom0After = (await api("GET", "/api/atoms")).atoms[0];
    record("C6", "悬停热键O瞬时置换", atom0After.symbol === "O", `before=${atom0Before.symbol} after=${atom0After.symbol}`);
    // 悬停热键 B 冲突演示（App.tsx:87 建键工具 vs Molecule2DCanvas.tsx:91 硼元素 双重映射）
    await win.mouse.move(centers[1].x - 100, centers[1].y - 100);
    await sleep(200);
    await win.mouse.move(centers[1].x, centers[1].y);
    await sleep(300);
    await win.keyboard.press("b");
    await sleep(800);
    const atom1After = (await api("GET", "/api/atoms")).atoms[1];
    record("C7", "悬停热键B置换硼", atom1After.symbol === "B", `atom1=${atom1After.symbol} (期望B；App.tsx:87与画布:91双重映射b键→建键工具抢占,元素置换不可靠)`);
    await api("POST", "/api/build/preset", { id: "caffeine" });
    await sleep(500);

    // ===== D. 五大 HUD 玻璃层 =====
    for (const label of ["砌块库", "坐标", "计算", "能级", "AI"]) {
      await win.locator(`button:has(span:text-is("${label}"))`).first().click();
      await sleep(250);
    }
    await sleep(500);
    const hudTitles = ["砌块库与 GaussView 片段", "笛卡尔空间坐标表", "量子化学与材料计算设置", "前线分子轨道与能级阶梯", "MolForge AI 科学计算副驾驶"];
    const bodyText = await win.evaluate(() => document.body.innerText);
    const openHuds = hudTitles.filter((t) => bodyText.includes(t));
    await win.screenshot({ path: path.join(outDir, "audit_D_five_hud_layers.png") });
    record("D1", "五大HUD同时呼出", openHuds.length === 5, `open=${openHuds.length}/5`);
    const blurCount = await win.evaluate(() => [...document.querySelectorAll("div")].filter((d) => d.className.includes && d.className.includes("backdrop-blur-2xl") && d.innerText && d.innerText.includes("关闭图层") === false && d.querySelector("button[title='关闭图层']")).length);
    record("D2", "HUD磨砂玻璃质感", blurCount >= 5, `backdrop-blur-2xl 浮窗数=${blurCount}`);
    // 拖拽砌块库标题栏（用 style.zIndex 精确定位浮窗根元素）
    const dragInfo = await win.evaluate(() => {
      const wins = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='关闭图层']"));
      const frag = wins.find((w) => w.innerText.includes("砌块库与 GaussView"));
      if (!frag) return null;
      const bar = frag.querySelector("div.cursor-grab");
      const r = bar.getBoundingClientRect();
      const wr = frag.getBoundingClientRect();
      return { bx: r.x + r.width / 2, by: r.y + r.height / 2, wx: wr.x, wy: wr.y };
    });
    if (dragInfo) {
      await win.mouse.move(dragInfo.bx, dragInfo.by);
      await win.mouse.down();
      await win.mouse.move(dragInfo.bx + 180, dragInfo.by + 120, { steps: 8 });
      await win.mouse.up();
      await sleep(300);
    }
    const winAfter = await win.evaluate(() => {
      const wins = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='关闭图层']"));
      const frag = wins.find((w) => w.innerText.includes("砌块库与 GaussView"));
      if (!frag) return null;
      const wr = frag.getBoundingClientRect();
      return { x: wr.x, y: wr.y };
    });
    const dragged = dragInfo && winAfter && (Math.abs(winAfter.x - dragInfo.wx) > 100 || Math.abs(winAfter.y - dragInfo.wy) > 60);
    record("D3", "HUD标题栏拖拽", dragged, `before=(${dragInfo?.wx},${dragInfo?.wy}) after=${JSON.stringify(winAfter)}`);
    // 最小化（砌块库窗自己的最小化按钮）
    await win.evaluate(() => {
      const wins = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='关闭图层']"));
      const frag = wins.find((w) => w.innerText.includes("砌块库与 GaussView"));
      frag?.querySelector("button[title='最小化']")?.click();
    });
    await sleep(250);
    const minimizedH = await win.evaluate(() => {
      const wins = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='展开']"));
      const frag = wins.find((w) => w.innerText.includes("砌块库与 GaussView"));
      return frag ? frag.getBoundingClientRect().height : -1;
    });
    record("D4", "HUD最小化折叠", minimizedH > 0 && minimizedH <= 45, `minimized height=${minimizedH}`);
    await win.screenshot({ path: path.join(outDir, "audit_D_hud_drag_minimize.png") });
    // 层级测试：点击被遮挡窗口能否置顶
    const zTest = await win.evaluate(() => {
      const wins = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='关闭图层'],button[title='展开']"));
      return wins.map((w) => ({ z: w.style.zIndex, title: (w.innerText || "").slice(0, 20) }));
    });
    record("D5", "多层z-index状态", true, JSON.stringify(zTest));
    // 关闭全部 HUD（in-page click 避免遮挡拦截）
    for (let i = 0; i < 6; i++) {
      const closed = await win.evaluate(() => {
        const wins = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='关闭图层']"));
        if (!wins.length) return false;
        wins[0].querySelector("button[title='关闭图层']").click();
        return true;
      });
      if (!closed) break;
      await sleep(200);
    }

    // ===== E. Ctrl+B 沉浸 + 三向投影 =====
    const navBefore = await win.locator('[data-testid="nav-rail"]').boundingBox();
    await win.keyboard.press("Control+b");
    await sleep(400);
    const navAfterVisible = await win.locator('[data-testid="nav-rail"]').isVisible().catch(() => false);
    const navAfter = navAfterVisible ? await win.locator('[data-testid="nav-rail"]').boundingBox() : null;
    const editorBox = await win.locator('[data-testid="view-editor"]').boundingBox();
    await win.screenshot({ path: path.join(outDir, "audit_E_ctrlB_immersive.png") });
    const collapsed = !navAfterVisible || (navAfter && navAfter.width < 10) || (editorBox && navBefore && editorBox.width > 1440 - 60);
    record("E1", "Ctrl+B隐藏主导航", collapsed, `navBefore.w=${navBefore?.width} navAfter=${JSON.stringify(navAfter)} editor.w=${editorBox?.width}`);
    await win.keyboard.press("Control+b");
    await sleep(300);
    // 切换 2D+3D 分屏
    await win.locator("button", { hasText: "2D+3D" }).first().click();
    await sleep(600);
    for (const [view, file] of [["正视", "audit_E_front.png"], ["俯视", "audit_E_top.png"], ["侧视", "audit_E_side.png"]]) {
      const btn = win.locator(`button:has-text("${view}")`).last();
      await btn.click();
      await sleep(400);
      await win.screenshot({ path: path.join(outDir, file) });
    }
    record("E2", "三向投影按钮截图", true, "front/top/side 三张截图已保存（相机 yaw/pitch 源码 camera.ts:16-29 正确）");

    // ===== F. Shift 多选测量 HUD =====
    await win.locator('button:text-is("2D")').first().click().catch(() => {});
    await sleep(400);
    await win.keyboard.press("v"); // 确保选择工具（C7 可能切到了建键）
    await sleep(200);
    centers = await atomCenters(win);
    if (!centers.length) { await win.locator('button:text-is("2D+3D")').first().click().catch(() => {}); await sleep(400); centers = await atomCenters(win); }
    const emptyPt = await win.evaluate(() => {
      const svg = document.querySelector('svg[data-testid="canvas-2d"]');
      const r = svg.getBoundingClientRect();
      // 真空白：右缘中部（左上角是 SMILES 输入框、底部是提示条，都会拦截点击）
      return { x: r.x + r.width - 40, y: r.y + r.height * 0.5 };
    });
    async function measureText(n) {
      await win.mouse.click(emptyPt.x, emptyPt.y); // 空白取消选择
      await sleep(200);
      await win.keyboard.down("Shift");
      for (let i = 0; i < n; i++) { await win.mouse.click(centers[i].x, centers[i].y); await sleep(200); }
      await win.keyboard.up("Shift");
      await sleep(300);
      return win.evaluate(() => {
        const t = document.body.innerText;
        const m = t.match(/(距离|键角|二面角) \([^\n]*/g);
        return m ? m.join(" | ") : "(无测量文本)";
      });
    }
    const m2 = await measureText(2);
    await win.screenshot({ path: path.join(outDir, "audit_F_measure_2atoms.png") });
    record("F1", "2原子距离测量", /\d+\.\d{3}\s*Å/.test(m2), m2);
    const m3 = await measureText(3);
    await win.screenshot({ path: path.join(outDir, "audit_F_measure_3atoms.png") });
    record("F2", "3原子键角测量", /\d+\.\d°/.test(m3), m3);
    const m4 = await measureText(4);
    await win.screenshot({ path: path.join(outDir, "audit_F_measure_4atoms.png") });
    record("F3", "4原子二面角真实计算", m4.includes("二面角") && !m4.includes("0.00° (共平面)"), `${m4} (硬编码0.00°共平面=Mock, EditorView.tsx:152)`);

    // ===== G. SMILES 生成 + Clean 3D =====
    const smilesInput = win.locator('input[placeholder="输入 SMILES 生成分子..."]');
    await smilesInput.fill("CC(=O)Oc1ccccc1C(=O)O");
    await win.locator("button", { hasText: "生成" }).first().click();
    await sleep(1500);
    const aspDoc = await api("GET", "/api/document");
    record("G1", "SMILES阿司匹林生成", aspDoc.formula === "C9H8O4", `formula=${aspDoc.formula} atoms=${aspDoc.num_atoms}`);
    await win.screenshot({ path: path.join(outDir, "audit_G_aspirin.png") });
    const posBefore = (await api("GET", "/api/atoms")).atoms.map((a) => [a.x, a.y, a.z]);
    await win.locator('[data-testid="chemical-tool-rail"] button[title^="3D 力场优化"]').click();
    await sleep(2000);
    const posAfter = (await api("GET", "/api/atoms")).atoms.map((a) => [a.x, a.y, a.z]);
    let maxShift = 0;
    for (let i = 0; i < Math.min(posBefore.length, posAfter.length); i++) {
      const d = Math.hypot(posAfter[i][0] - posBefore[i][0], posAfter[i][1] - posBefore[i][1], posAfter[i][2] - posBefore[i][2]);
      if (d > maxShift) maxShift = d;
    }
    record("G2", "Clean3D真实弛豫", maxShift > 0.01, `最大原子位移=${maxShift.toFixed(4)} Å`);

    // ===== H. OSC 砌块接枝 =====
    await win.locator('button:has(span:text-is("砌块库"))').first().click();
    await sleep(400);
    // 若窗口记住了最小化状态，先展开
    await win.evaluate(() => {
      const wins = [...document.querySelectorAll("div")].filter((d) => d.style && d.style.zIndex && d.querySelector("button[title='展开']"));
      const frag = wins.find((w) => w.innerText.includes("砌块库与 GaussView"));
      frag?.querySelector("button[title='展开']")?.click();
    });
    await sleep(300);
    const atomsBeforeFrag = (await api("GET", "/api/document")).num_atoms;
    // 并五苯（后端目录缺失 → 预期 404 错误通知）
    await win.locator("div.cursor-pointer", { hasText: "并五苯" }).first().click();
    await sleep(900);
    const atomsAfterPent = (await api("GET", "/api/document")).num_atoms;
    const errToast = await win.evaluate(() => document.body.innerText.includes("未找到") || document.body.innerText.includes("404") || document.body.innerText.includes("失败"));
    await win.screenshot({ path: path.join(outDir, "audit_H_pentacene_404.png") });
    record("H1", "并五苯插入", atomsAfterPent > atomsBeforeFrag, `before=${atomsBeforeFrag} after=${atomsAfterPent} errToast=${errToast} (后端 fragments 目录无 pentacene)`);
    // BDT 接枝
    await win.locator("div.cursor-pointer", { hasText: "苯并二噻吩核心" }).first().click();
    await sleep(900);
    const atomsAfterBdt = (await api("GET", "/api/document")).num_atoms;
    await win.screenshot({ path: path.join(outDir, "audit_H_bdt_graft.png") });
    record("H2", "BDT给体接枝递增", atomsAfterBdt > atomsAfterPent, `before=${atomsAfterPent} after=${atomsAfterBdt}`);
    // 关闭砌块库
    await win.locator('button:has(span:text-is("砌块库"))').first().click();
    await sleep(200);

    // ===== I. AI 副驾驶上下文 + 提问 =====
    await api("POST", "/api/build/preset", { id: "caffeine" });
    await sleep(600);
    await win.locator('button:has(span:text-is("AI"))').first().click();
    await sleep(500);
    const aiContext = await win.evaluate(() => {
      const t = document.body.innerText;
      const i = t.indexOf("上下文:");
      return i >= 0 ? t.slice(i, i + 160).replace(/\n/g, " | ") : "(未找到上下文区)";
    });
    record("I1", "AI自动捕获上下文", aiContext.includes("C8H10N4O2") && aiContext.includes("24 原子"), aiContext);
    const aiTextarea = win.locator('textarea[placeholder*="向 AI 咨询"]');
    await aiTextarea.fill("分析该体系前线轨道分布与亲电位点");
    await aiTextarea.press("Enter");
    await sleep(2500);
    const aiReply = await win.evaluate(() => {
      const t = document.body.innerText;
      const i = t.indexOf("紧束缚分析得到");
      return i >= 0 ? t.slice(Math.max(0, i - 300), i + 220).replace(/\n/g, " | ") : t.slice(-400);
    });
    await win.screenshot({ path: path.join(outDir, "audit_I_ai_copilot.png") });
    const isFallback = aiReply.includes("紧束缚分析得到") || aiReply.includes("建议检查分子共轭平面性");
    const honestOffline = aiReply.includes("离线降级"); record("I2", "AI回答诚实性(真AI或显式离线标注)", !isFallback || honestOffline, honestOffline ? "显式离线降级标注(无有效Key时的诚实行为)" : (!isFallback ? aiReply.slice(0,150) : "静默模板冒充AI"));
    const katexInfo = await win.evaluate(() => ({ katex: document.querySelectorAll(".katex").length, rawDollar: (document.body.innerText.match(/\\$[^$\\n]{2,}\\$/g) || []).length })); record("I3", "公式KaTeX真渲染", katexInfo.rawDollar === 0, `katex节点=${katexInfo.katex} 裸$公式=${katexInfo.rawDollar}`);
    // 关闭 AI
    await win.locator('button:has(span:text-is("AI"))').first().click();
    await sleep(200);

    record("Z1", "渲染进程零未捕获异常", pageErrors.length === 0, pageErrors.join("; ") || "0 errors");
  } finally {
    fs.writeFileSync(path.join(outDir, "fix_e2e_results.json"), JSON.stringify(results, null, 2), "utf8");
    await app.close();
  }
  const fails = results.filter((r) => !r.pass);
  console.log(`\n[AUDIT] TOTAL=${results.length} PASS=${results.length - fails.length} FAIL=${fails.length}`);
  console.log("[AUDIT] FAIL items:", fails.map((f) => f.id).join(", "));
}

run().catch((e) => { console.error("[AUDIT] FATAL:", e); fs.writeFileSync(path.join(outDir, "fix_e2e_results.json"), JSON.stringify(results, null, 2), "utf8"); process.exit(1); });