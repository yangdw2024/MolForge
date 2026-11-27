import { app, BrowserWindow, dialog, ipcMain, session, shell } from "electron";
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import fsPromises from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  ALLOWED_READ_EXTENSIONS,
  ALLOWED_WRITE_EXTENSIONS,
  buildDesktopCsp,
  isAllowedExternalUrl,
  sanitizeFilePath,
} from "./security.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BRIDGE_HOST = "127.0.0.1";
const BRIDGE_PORT = 18765;

interface WindowBounds {
  width: number;
  height: number;
  x?: number;
  y?: number;
  maximized?: boolean;
}

interface RecentProjectEntry {
  name: string;
  path: string;
  formula?: string;
  numAtoms?: number;
  updatedAt: string;
}

interface StudioPersistedState {
  schemaVersion: number;
  theme: "obsidian" | "arctic";
  reducedMotion: boolean;
  uiDensity: "compact" | "comfortable";
  navExpanded: boolean;
  layoutMode: "split" | "3d" | "2d";
  inspectorWidth: number;
  splitRatio: number;
  autosaveEnabled: boolean;
  windowBounds: WindowBounds;
  recentProjects: RecentProjectEntry[];
  recentAnalyses: Array<{
    analysisId: string;
    title: string;
    moleculeName: string;
    status: string;
    timestamp: string;
  }>;
  libraryCustomMolecules: Array<Record<string, unknown>>;
}

const DEFAULT_STUDIO_STATE: StudioPersistedState = {
  schemaVersion: 1,
  theme: "obsidian",
  reducedMotion: false,
  uiDensity: "compact",
  navExpanded: true,
  layoutMode: "split",
  inspectorWidth: 320,
  splitRatio: 0.44,
  autosaveEnabled: true,
  windowBounds: { width: 1440, height: 880 },
  recentProjects: [],
  recentAnalyses: [],
  libraryCustomMolecules: [],
};

let mainWindow: BrowserWindow | null = null;
let bridgeProcess: ChildProcess | null = null;
let bridgeStartedByApp = false;

function userDataDir(): string {
  return app.getPath("userData");
}

function stateFilePath(): string {
  return path.join(userDataDir(), "studio-state.json");
}

function autosavePaths(): { data: string; meta: string } {
  const dir = path.join(userDataDir(), "autosave");
  fs.mkdirSync(dir, { recursive: true });
  return {
    data: path.join(dir, "recovery.mforge"),
    meta: path.join(dir, "recovery.meta.json"),
  };
}

async function atomicWriteBuffer(targetPath: string, data: Buffer): Promise<void> {
  const dir = path.dirname(targetPath);
  await fsPromises.mkdir(dir, { recursive: true });
  const tmpPath = `${targetPath}.tmp.${process.pid}.${Date.now()}`;
  const handle = await fsPromises.open(tmpPath, "w");
  try {
    await handle.writeFile(data);
    await handle.sync();
  } finally {
    await handle.close();
  }
  if (fs.existsSync(targetPath)) {
    const bakPath = `${targetPath}.bak`;
    try {
      await fsPromises.copyFile(targetPath, bakPath);
    } catch {
      // ignore backup failure if unreadable
    }
  }
  await fsPromises.rename(tmpPath, targetPath);
}

async function loadPersistedState(): Promise<StudioPersistedState> {
  const f = stateFilePath();
  for (const candidate of [f, `${f}.bak`]) {
    try {
      if (!fs.existsSync(candidate)) continue;
      const raw = await fsPromises.readFile(candidate, "utf-8");
      const parsed = JSON.parse(raw) as Partial<StudioPersistedState>;
      if (parsed && typeof parsed === "object") {
        return {
          ...DEFAULT_STUDIO_STATE,
          ...parsed,
          windowBounds: {
            ...DEFAULT_STUDIO_STATE.windowBounds,
            ...(parsed.windowBounds ?? {}),
          },
          recentProjects: Array.isArray(parsed.recentProjects)
            ? parsed.recentProjects
            : [],
          recentAnalyses: Array.isArray(parsed.recentAnalyses)
            ? parsed.recentAnalyses
            : [],
          libraryCustomMolecules: Array.isArray(parsed.libraryCustomMolecules)
            ? parsed.libraryCustomMolecules
            : [],
        };
      }
    } catch {
      // fall through to backup or default
    }
  }
  return { ...DEFAULT_STUDIO_STATE };
}

async function savePersistedState(
  patch: Partial<StudioPersistedState>
): Promise<StudioPersistedState> {
  const current = await loadPersistedState();
  const next: StudioPersistedState = {
    ...current,
    ...patch,
    windowBounds: {
      ...current.windowBounds,
      ...(patch.windowBounds ?? {}),
    },
  };
  await atomicWriteBuffer(
    stateFilePath(),
    Buffer.from(JSON.stringify(next, null, 2), "utf-8")
  );
  return next;
}

function isBridgePortListening(): Promise<boolean> {
  return new Promise((resolve) => {
    const sock = net.connect({ host: BRIDGE_HOST, port: BRIDGE_PORT });
    const done = (ok: boolean) => {
      sock.removeAllListeners();
      sock.destroy();
      resolve(ok);
    };
    sock.setTimeout(300);
    sock.once("connect", () => done(true));
    sock.once("timeout", () => done(false));
    sock.once("error", () => done(false));
  });
}

function resolvePythonBridgeLaunch(): {
  kind: "rust-core" | "bundled-exe" | "python";
  executable: string;
  args: string[];
  molforgeRoot: string;
  workDir: string;
} | null {
  const repoRoots = [
    process.env.MOLFORGE_REPO_ROOT,
    path.resolve(__dirname, "..", "..", "MolForge"),
    "E:\\YDW\\Trae_Chemdraw\\MolForge",
  ].filter((p): p is string => Boolean(p && fs.existsSync(p)));
  const molforgeRoot = repoRoots[0] ?? "";

  // 1. 优先查找纯 Rust 原生核心 (molforge-server.exe) —— 零 Python 依赖即可启动
  const rustCoreCandidates = [
    path.join(process.resourcesPath, "core", "molforge-server.exe"),
    path.resolve(__dirname, "..", "resources", "core", "molforge-server.exe"),
    path.resolve(__dirname, "..", "..", "molforge-core", "target", "release", "molforge-server.exe"),
  ];
  const rustCoreExe = rustCoreCandidates.find((p) => fs.existsSync(p));
  if (rustCoreExe) {
    return {
      kind: "rust-core",
      executable: rustCoreExe,
      args: [],
      molforgeRoot,
      workDir: path.dirname(rustCoreExe),
    };
  }

  // 2. 次选随应用打包的旧版免 Python 内核 (molforge-bridge.exe)
  const bundledCandidates = [
    path.join(process.resourcesPath, "bridge", "molforge-bridge", "molforge-bridge.exe"),
    path.resolve(__dirname, "..", "resources", "bridge", "molforge-bridge", "molforge-bridge.exe"),
  ];
  const bundledExe = bundledCandidates.find((p) => fs.existsSync(p));

  if (bundledExe) {
    return {
      kind: "bundled-exe",
      executable: bundledExe,
      args: ["--host", BRIDGE_HOST, "--port", String(BRIDGE_PORT)],
      molforgeRoot,
      workDir: path.dirname(bundledExe),
    };
  }

  // 3. 回退到本机 Python 运行时
  const envPy = process.env.MOLFORGE_PYTHON;
  const candidates = [
    envPy,
    "D:\\YDW\\Trae_Gromacs\\miniconda3\\envs\\molforge-webengine\\python.exe",
    "python",
  ].filter((p): p is string => Boolean(p && p.trim()));

  const pythonExe = candidates.find((p) => p === "python" || fs.existsSync(p));
  if (!pythonExe) return null;
  return {
    kind: "python",
    executable: pythonExe,
    args: ["-B", "-m", "molforge.server.api_bridge", "--host", BRIDGE_HOST, "--port", String(BRIDGE_PORT)],
    molforgeRoot,
    workDir: molforgeRoot ? path.dirname(molforgeRoot) : app.getPath("userData"),
  };
}

async function ensurePythonBridge(): Promise<{ ok: boolean; detail: string }> {
  if (await isBridgePortListening()) {
    return { ok: true, detail: "attached-existing" };
  }
  const cfg = resolvePythonBridgeLaunch();
  if (!cfg) {
    return {
      ok: false,
      detail: "未检测到内置或外部 MolForge 化学计算内核",
    };
  }
  if (bridgeProcess && !bridgeProcess.killed) {
    bridgeProcess.kill();
    bridgeProcess = null;
  }

  const pyPath = [cfg.molforgeRoot, "E:\\YDW\\Trae_Gaussian"]
    .filter((p) => fs.existsSync(p))
    .join(";");
  const localDataDir =
    cfg.molforgeRoot && fs.existsSync(path.join(cfg.molforgeRoot, "user_data"))
      ? path.join(cfg.molforgeRoot, "user_data")
      : path.join(app.getPath("userData"), "bridge_data");

  bridgeProcess = spawn(cfg.executable, cfg.args, {
    cwd: cfg.workDir,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      MOLFORGE_HOST: BRIDGE_HOST,
      MOLFORGE_PORT: String(BRIDGE_PORT),
      PYTHONPATH: pyPath,
      MOLFORGE_DATA_DIR: localDataDir,
      MOLFORGE_ALLOW_ANY_DRIVE: "1",
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONUTF8: "1",
    },
  });
  bridgeStartedByApp = true;

  bridgeProcess.on("exit", () => {
    bridgeProcess = null;
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("engine:status-changed", {
        connected: false,
      });
    }
  });

  for (let i = 0; i < 60; i++) {
    if (await isBridgePortListening()) {
      return { ok: true, detail: `spawned:${cfg.kind}` };
    }
    await new Promise((r) => setTimeout(r, 150));
  }
  return { ok: false, detail: "化学引擎桥接服务启动超时" };
}

function registerCsp(isDev: boolean): void {
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    const url = details.url || "";
    if (!url.startsWith("http://127.0.0.1:5178") && !url.startsWith("file://")) {
      callback({ responseHeaders: details.responseHeaders });
      return;
    }
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [buildDesktopCsp(isDev)],
      },
    });
  });
}

async function createMainWindow(): Promise<void> {
  const persisted = await loadPersistedState();
  const isDev = Boolean(process.env.VITE_DEV_SERVER_URL);
  registerCsp(isDev);

  const iconPath = path.resolve(__dirname, "..", "build", "icon.png");
  const preloadPath = path.resolve(__dirname, "preload.cjs");

  mainWindow = new BrowserWindow({
    width: Math.max(1024, persisted.windowBounds.width || 1440),
    height: Math.max(680, persisted.windowBounds.height || 880),
    x: persisted.windowBounds.x,
    y: persisted.windowBounds.y,
    minWidth: 1024,
    minHeight: 680,
    frame: false,
    title: "MolForge Studio",
    backgroundColor: persisted.theme === "arctic" ? "#F5F7FA" : "#0B1220",
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });

  if (persisted.windowBounds.maximized) {
    mainWindow.maximize();
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedExternalUrl(url)) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    const allowedLocal =
      url.startsWith("file://") || url.startsWith("http://127.0.0.1:5178");
    if (!allowedLocal) {
      event.preventDefault();
    }
  });

  const emitMaxState = () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send(
        "window:maximized-changed",
        mainWindow.isMaximized()
      );
    }
  };
  mainWindow.on("maximize", emitMaxState);
  mainWindow.on("unmaximize", emitMaxState);

  mainWindow.on("close", () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    const isMax = mainWindow.isMaximized();
    const bounds = isMax ? mainWindow.getNormalBounds() : mainWindow.getBounds();
    void savePersistedState({
      windowBounds: {
        width: bounds.width,
        height: bounds.height,
        x: bounds.x,
        y: bounds.y,
        maximized: isMax,
      },
    });
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    await mainWindow.loadURL(devUrl);
  } else {
    await mainWindow.loadFile(path.resolve(__dirname, "..", "dist", "index.html"));
  }
}

function registerIpcHandlers(): void {
  ipcMain.handle("win:minimize", () => {
    mainWindow?.minimize();
  });
  ipcMain.handle("win:toggleMaximize", () => {
    if (!mainWindow) return false;
    if (mainWindow.isMaximized()) mainWindow.unmaximize();
    else mainWindow.maximize();
    return mainWindow.isMaximized();
  });
  ipcMain.handle("win:close", () => {
    mainWindow?.close();
  });
  ipcMain.handle("win:isMaximized", () => mainWindow?.isMaximized() ?? false);

  ipcMain.handle("dialog:openStructure", async () => {
    if (!mainWindow) return { cancelled: true };
    const res = await dialog.showOpenDialog(mainWindow, {
      title: "打开分子结构或 MolForge 工程",
      properties: ["openFile"],
      filters: [
        {
          name: "分子结构与工程",
          extensions: ["mforge", "pdb", "xyz", "mol", "sdf", "cif", "mol2"],
        },
        { name: "所有文件", extensions: ["*"] },
      ],
    });
    if (res.canceled || res.filePaths.length === 0) return { cancelled: true };
    return { cancelled: false, filePath: res.filePaths[0] };
  });

  ipcMain.handle("dialog:openProject", async () => {
    if (!mainWindow) return { cancelled: true };
    const res = await dialog.showOpenDialog(mainWindow, {
      title: "打开 MolForge 工程 (.mforge)",
      properties: ["openFile"],
      filters: [{ name: "MolForge 工程", extensions: ["mforge"] }],
    });
    if (res.canceled || res.filePaths.length === 0) return { cancelled: true };
    return { cancelled: false, filePath: res.filePaths[0] };
  });

  ipcMain.handle("dialog:openQcLog", async () => {
    if (!mainWindow) return { cancelled: true };
    const res = await dialog.showOpenDialog(mainWindow, {
      title: "打开 Gaussian / ORCA / Multiwfn 量化或波函数文件",
      properties: ["openFile"],
      filters: [
        { name: "量化与波函数文件", extensions: ["fchk", "fch", "log", "out", "wfn", "wfx", "molden", "mwfn"] },
      ],
    });
    if (res.canceled || res.filePaths.length === 0) return { cancelled: true };
    return { cancelled: false, filePath: res.filePaths[0] };
  });

  ipcMain.handle("dialog:openExecutable", async () => {
    if (!mainWindow) return { cancelled: true };
    const res = await dialog.showOpenDialog(mainWindow, {
      title: "选择科学计算引擎可执行文件",
      properties: ["openFile"],
      filters: [
        { name: "可执行程序 (*.exe)", extensions: ["exe"] },
        { name: "所有文件", extensions: ["*"] },
      ],
    });
    if (res.canceled || res.filePaths.length === 0) return { cancelled: true };
    return { cancelled: false, filePath: res.filePaths[0] };
  });

  ipcMain.handle(
    "dialog:saveFile",
    async (
      _event,
      payload: {
        defaultName?: string;
        filters?: Array<{ name: string; extensions: string[] }>;
      }
    ) => {
      if (!mainWindow) return { cancelled: true };
      const res = await dialog.showSaveDialog(mainWindow, {
        title: "保存 / 导出文件",
        defaultPath: payload?.defaultName || "molecule.mforge",
        filters: payload?.filters ?? [
          { name: "MolForge 工程 (*.mforge)", extensions: ["mforge"] },
        ],
      });
      if (res.canceled || !res.filePath) return { cancelled: true };
      return { cancelled: false, filePath: res.filePath };
    }
  );

  ipcMain.handle(
    "fs:writeTextAtomic",
    async (_event, payload: { targetPath: string; content: string }) => {
      const check = sanitizeFilePath(payload?.targetPath, ALLOWED_WRITE_EXTENSIONS);
      if (!check.ok) throw new Error(check.error);
      if (typeof payload?.content !== "string") {
        throw new Error("写入内容必须为字符串");
      }
      await atomicWriteBuffer(
        check.resolved,
        Buffer.from(payload.content, "utf-8")
      );
      return { ok: true, path: check.resolved };
    }
  );

  ipcMain.handle(
    "fs:writeBase64Atomic",
    async (_event, payload: { targetPath: string; base64Data: string }) => {
      const check = sanitizeFilePath(payload?.targetPath, ALLOWED_WRITE_EXTENSIONS);
      if (!check.ok) throw new Error(check.error);
      if (typeof payload?.base64Data !== "string") {
        throw new Error("Base64 数据无效");
      }
      await atomicWriteBuffer(
        check.resolved,
        Buffer.from(payload.base64Data, "base64")
      );
      return { ok: true, path: check.resolved };
    }
  );

  ipcMain.handle(
    "fs:readBase64",
    async (_event, payload: { targetPath: string }) => {
      const check = sanitizeFilePath(payload?.targetPath, ALLOWED_READ_EXTENSIONS);
      if (!check.ok) throw new Error(check.error);
      const buf = await fsPromises.readFile(check.resolved);
      return { ok: true, path: check.resolved, base64Data: buf.toString("base64") };
    }
  );

  ipcMain.handle(
    "fs:readText",
    async (_event, payload: { targetPath: string }) => {
      const check = sanitizeFilePath(payload?.targetPath, ALLOWED_READ_EXTENSIONS);
      if (!check.ok) throw new Error(check.error);
      const text = await fsPromises.readFile(check.resolved, "utf-8");
      return { ok: true, path: check.resolved, content: text };
    }
  );

  ipcMain.handle("state:load", () => loadPersistedState());
  ipcMain.handle(
    "state:save",
    (_event, patch: Partial<StudioPersistedState>) => savePersistedState(patch)
  );

  ipcMain.handle(
    "autosave:save",
    async (
      _event,
      payload: { base64Data: string; meta: Record<string, unknown> }
    ) => {
      const paths = autosavePaths();
      await atomicWriteBuffer(
        paths.data,
        Buffer.from(payload.base64Data, "base64")
      );
      await atomicWriteBuffer(
        paths.meta,
        Buffer.from(
          JSON.stringify({ ...payload.meta, savedAt: new Date().toISOString() }),
          "utf-8"
        )
      );
      return { ok: true };
    }
  );

  ipcMain.handle("autosave:load", async () => {
    const paths = autosavePaths();
    if (!fs.existsSync(paths.data) || !fs.existsSync(paths.meta)) {
      return { available: false };
    }
    try {
      const meta = JSON.parse(await fsPromises.readFile(paths.meta, "utf-8"));
      const raw = await fsPromises.readFile(paths.data);
      return { available: true, meta, base64Data: raw.toString("base64") };
    } catch {
      return { available: false };
    }
  });

  ipcMain.handle("autosave:clear", async () => {
    const paths = autosavePaths();
    for (const f of [paths.data, paths.meta]) {
      if (fs.existsSync(f)) await fsPromises.unlink(f);
    }
    return { ok: true };
  });

  ipcMain.handle("sys:telemetry", () => {
    const mem = process.memoryUsage();
    return {
      appVersion: app.getVersion(),
      electronVersion: process.versions.electron,
      platform: os.platform(),
      arch: os.arch(),
      rssMb: Math.round(mem.rss / (1024 * 1024)),
      sysFreeGb: Number((os.freemem() / 1024 ** 3).toFixed(1)),
      sysTotalGb: Number((os.totalmem() / 1024 ** 3).toFixed(1)),
    };
  });

  ipcMain.handle("sys:openExternal", async (_event, rawUrl: string) => {
    if (!isAllowedExternalUrl(rawUrl)) {
      throw new Error("仅允许打开安全的 HTTPS 外部链接");
    }
    await shell.openExternal(rawUrl);
    return { ok: true };
  });

  ipcMain.handle("engine:restart", () => ensurePythonBridge());
}

app.whenReady().then(async () => {
  // 渲染层只与本地回环桥接通信（无任何外网 fetch）；强制直连，
  // 避免系统代理（Clash 等）劫持 127.0.0.1 请求导致内核被误判离线。
  await session.defaultSession.setProxy({ proxyRules: "direct://" });
  registerIpcHandlers();
  await ensurePythonBridge();
  await createMainWindow();
});

app.on("window-all-closed", () => {
  if (bridgeStartedByApp && bridgeProcess && !bridgeProcess.killed) {
    bridgeProcess.kill();
    bridgeProcess = null;
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});
