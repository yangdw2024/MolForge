/**
 * MolForge Studio Node.js Programmatic API
 */
import { spawn } from 'node:child_process';

export function launchMolForge(args = [], options = {}) {
  const defaultArgs = ['--welcome', ...args];
  return spawn('node', [new URL('./bin/molforge.js', import.meta.url).pathname, ...defaultArgs], {
    stdio: 'inherit',
    ...options
  });
}

export default { launchMolForge };
