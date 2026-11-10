#!/usr/bin/env node

import { spawn, spawnSync } from 'node:child_process';
import process from 'node:process';
import path from 'node:path';
import fs from 'node:fs';

function isHealthyPython(cmd, args = []) {
  try {
    const res = spawnSync(cmd, [...args, '-c', 'import sys; sys.exit(0)'], {
      stdio: 'ignore',
      timeout: 3000
    });
    return res.status === 0;
  } catch {
    return false;
  }
}

function findPython() {
  if (process.env.MOLFORGE_PYTHON && isHealthyPython(process.env.MOLFORGE_PYTHON)) {
    return { cmd: process.env.MOLFORGE_PYTHON, args: [] };
  }

  // Probe Conda environment 'molforge-webengine'
  const condaEnvs = [
    'D:\\YDW\\Trae_Gromacs\\miniconda3\\envs\\molforge-webengine\\python.exe',
    'C:\\ProgramData\\miniconda3\\envs\\molforge-webengine\\python.exe',
    'D:\\miniconda3\\envs\\molforge-webengine\\python.exe'
  ];
  for (const cpy of condaEnvs) {
    if (fs.existsSync(cpy) && isHealthyPython(cpy)) {
      return { cmd: cpy, args: [] };
    }
  }

  // Windows standard Python installations
  const localAppData = process.env.LOCALAPPDATA || 'C:\\Users\\Administrator\\AppData\\Local';
  const py312 = path.join(localAppData, 'Programs', 'Python', 'Python312', 'python.exe');

  if (process.platform === 'win32') {
    if (fs.existsSync(py312) && isHealthyPython(py312)) {
      return { cmd: py312, args: [] };
    }
    if (isHealthyPython('py', ['-3.12'])) {
      return { cmd: 'py', args: ['-3.12'] };
    }
    if (isHealthyPython('python3')) {
      return { cmd: 'python3', args: [] };
    }
    if (isHealthyPython('python')) {
      return { cmd: 'python', args: [] };
    }
  } else {
    for (const cmd of ['python3', 'python']) {
      if (isHealthyPython(cmd)) {
        return { cmd, args: [] };
      }
    }
  }
  return null;
}

function checkMolForgeInstalled(pyObj) {
  try {
    const res = spawnSync(pyObj.cmd, [...pyObj.args, '-c', 'import sys, molforge; sys.exit(0)'], {
      stdio: 'ignore',
      timeout: 5000
    });
    return res.status === 0;
  } catch {
    return false;
  }
}

const args = process.argv.slice(2);
const pyObj = findPython();

if (!pyObj) {
  console.error('Error: A working Python 3.10+ runtime was not found.');
  console.error('Please ensure Python is installed or set the MOLFORGE_PYTHON environment variable.');
  process.exit(1);
}

// Handle top-level install shortcut: npx @yangdw2024/molforge install
if (args[0] === 'install') {
  console.log(`[MolForge] Installing or updating molforge-studio via pip (${pyObj.cmd})...`);
  const child = spawn(pyObj.cmd, [...pyObj.args, '-m', 'pip', 'install', '-U', 'molforge-studio'], {
    stdio: 'inherit'
  });
  child.on('exit', (code) => process.exit(code || 0));
} else {
  // Check if molforge is installed or if we are in local repo
  const localLaunch = path.resolve(process.cwd(), 'scripts', 'launch.py');
  if (fs.existsSync(localLaunch)) {
    // Run local repo scripts/launch.py
    const child = spawn(pyObj.cmd, [...pyObj.args, localLaunch, ...args], {
      stdio: 'inherit'
    });
    child.on('exit', (code) => process.exit(code || 0));
  } else {
    if (!checkMolForgeInstalled(pyObj)) {
      console.log('[MolForge] molforge-studio is not currently installed in this Python environment.');
      console.log('[MolForge] Automatically running: pip install molforge-studio ...');
      const inst = spawnSync(pyObj.cmd, [...pyObj.args, '-m', 'pip', 'install', 'molforge-studio'], {
        stdio: 'inherit'
      });
      if (inst.status !== 0) {
        console.warn('[MolForge] Could not auto-install via pip. Trying to launch module directly...');
      }
    }
    const child = spawn(pyObj.cmd, [...pyObj.args, '-m', 'molforge', ...args], {
      stdio: 'inherit'
    });
    child.on('exit', (code) => process.exit(code || 0));
  }
}
