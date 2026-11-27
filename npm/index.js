import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

export const VERSION = '8.1.0';
export const RELEASE_URL = `https://github.com/yangdw2024/MolForge/releases/tag/v${VERSION}`;

function isRunnable(filePath) {
  try {
    if (!filePath) return false;
    const st = fs.statSync(filePath);
    if (!st.isFile()) return false;
    if (process.platform !== 'win32') {
      fs.accessSync(filePath, fs.constants.X_OK);
    }
    return true;
  } catch {
    return false;
  }
}

function searchPath(exeName) {
  const envPath = process.env.PATH || '';
  for (const dir of envPath.split(path.delimiter)) {
    if (!dir) continue;
    const cand = path.join(dir, exeName);
    if (isRunnable(cand)) return cand;
  }
  return null;
}

export function findStudioBinary() {
  const explicit = process.env.MOLFORGE_STUDIO_BIN?.trim();
  if (explicit) return isRunnable(explicit) ? path.resolve(explicit) : null;

  const exe = process.platform === 'win32' ? 'MolForge Studio.exe' : 'molforge-studio';
  const cwd = process.cwd();
  const candidates = [
    path.resolve(cwd, 'desktop', 'release', 'win-unpacked', exe),
    path.resolve(cwd, 'release', 'win-unpacked', exe),
  ];
  if (process.platform === 'win32') {
    const localApp = process.env.LOCALAPPDATA || '';
    if (localApp) {
      candidates.push(path.join(localApp, 'Programs', 'MolForge Studio', exe));
    }
  }
  for (const cand of candidates) {
    if (isRunnable(cand)) return cand;
  }
  return searchPath(exe);
}

export function findServerBinary() {
  const explicit = process.env.MOLFORGE_SERVER_BIN?.trim();
  if (explicit) return isRunnable(explicit) ? path.resolve(explicit) : null;

  const exe = process.platform === 'win32' ? 'molforge-server.exe' : 'molforge-server';
  const cwd = process.cwd();
  const candidates = [
    path.resolve(cwd, 'desktop', 'resources', 'core', exe),
    path.resolve(cwd, 'molforge-core', 'target', 'release', exe),
    path.resolve(cwd, 'target', 'release', exe),
  ];
  if (process.platform === 'win32') {
    const localApp = process.env.LOCALAPPDATA || '';
    if (localApp) {
      candidates.push(path.join(localApp, 'Programs', 'MolForge Studio', 'resources', 'core', exe));
    }
  }
  for (const cand of candidates) {
    if (isRunnable(cand)) return cand;
  }
  return searchPath(exe);
}

export function launchMolForge(args = [], options = {}) {
  const studio = findStudioBinary();
  if (!studio) {
    throw new Error(`MolForge Studio binary not found. Download v${VERSION} from ${RELEASE_URL}`);
  }
  return spawn(studio, args, { stdio: 'inherit', ...options });
}

export function launchServer(args = [], options = {}) {
  const srv = findServerBinary();
  if (!srv) {
    throw new Error(`molforge-server binary not found. Download v${VERSION} from ${RELEASE_URL}`);
  }
  return spawn(srv, args, { stdio: 'inherit', ...options });
}

export default {
  VERSION,
  RELEASE_URL,
  findStudioBinary,
  findServerBinary,
  launchMolForge,
  launchServer,
};
