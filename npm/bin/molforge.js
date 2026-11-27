#!/usr/bin/env node

import process from 'node:process';
import {
  VERSION,
  RELEASE_URL,
  findStudioBinary,
  findServerBinary,
  launchMolForge,
  launchServer,
} from '../index.js';

const args = process.argv.slice(2);

if (args.includes('--version') || args.includes('-v')) {
  console.log(`@yangdw2024/molforge v${VERSION}`);
  process.exit(0);
}

if (args.includes('--help') || args.includes('-h')) {
  console.log(`MolForge Studio v${VERSION} CLI wrapper

Usage:
  molforge [options] [args...]

Options:
  -v, --version   Show version
  --status        Show detected desktop/server binary paths
  --server        Launch headless Rust molforge-server (:18765)
  -h, --help      Show help

Download v${VERSION} installers:
  ${RELEASE_URL}`);
  process.exit(0);
}

if (args.includes('--status')) {
  console.log(
    JSON.stringify(
      {
        version: VERSION,
        studioBin: findStudioBinary(),
        serverBin: findServerBinary(),
        releases: RELEASE_URL,
      },
      null,
      2
    )
  );
  process.exit(0);
}

try {
  const isServer = args[0] === '--server' || args[0] === 'server';
  const child = isServer
    ? launchServer(args.slice(1))
    : launchMolForge(args);
  child.on('exit', (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else process.exit(code ?? 0);
  });
} catch (err) {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
}
