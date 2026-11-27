"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const ALLOWED_EVENTS = new Set([
  "window:maximized-changed",
  "engine:status-changed",
  "app:file-dropped",
]);

contextBridge.exposeInMainWorld("molforgeDesktop", {
  isElectron: true,
  windowControls: {
    minimize: () => ipcRenderer.invoke("win:minimize"),
    toggleMaximize: () => ipcRenderer.invoke("win:toggleMaximize"),
    close: () => ipcRenderer.invoke("win:close"),
    isMaximized: () => ipcRenderer.invoke("win:isMaximized"),
  },
  dialogs: {
    openStructureFile: () => ipcRenderer.invoke("dialog:openStructure"),
    openProjectFile: () => ipcRenderer.invoke("dialog:openProject"),
    openQcLogFile: () => ipcRenderer.invoke("dialog:openQcLog"),
    openExecutableFile: () => ipcRenderer.invoke("dialog:openExecutable"),
    saveFile: (defaultName, filters) =>
      ipcRenderer.invoke("dialog:saveFile", { defaultName, filters }),
  },
  files: {
    writeTextAtomic: (targetPath, content) =>
      ipcRenderer.invoke("fs:writeTextAtomic", { targetPath, content }),
    writeBase64Atomic: (targetPath, base64Data) =>
      ipcRenderer.invoke("fs:writeBase64Atomic", { targetPath, base64Data }),
    readBase64: (targetPath) =>
      ipcRenderer.invoke("fs:readBase64", { targetPath }),
    readText: (targetPath) =>
      ipcRenderer.invoke("fs:readText", { targetPath }),
  },
  workspace: {
    loadStudioState: () => ipcRenderer.invoke("state:load"),
    saveStudioState: (patch) => ipcRenderer.invoke("state:save", patch),
    saveAutosaveBase64: (base64Data, meta) =>
      ipcRenderer.invoke("autosave:save", { base64Data, meta }),
    loadAutosave: () => ipcRenderer.invoke("autosave:load"),
    clearAutosave: () => ipcRenderer.invoke("autosave:clear"),
  },
  system: {
    getTelemetry: () => ipcRenderer.invoke("sys:telemetry"),
    openExternalHttps: (url) => ipcRenderer.invoke("sys:openExternal", url),
    restartBridge: () => ipcRenderer.invoke("engine:restart"),
  },
  onEvent: (channel, handler) => {
    if (!ALLOWED_EVENTS.has(channel) || typeof handler !== "function") {
      return () => {};
    }
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
  },
});
