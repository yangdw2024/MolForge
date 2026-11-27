import { ChildProcess, SpawnOptions } from 'node:child_process';

export declare const VERSION: string;
export declare const RELEASE_URL: string;

export declare function findStudioBinary(): string | null;
export declare function findServerBinary(): string | null;
export declare function launchMolForge(args?: string[], options?: SpawnOptions): ChildProcess;
export declare function launchServer(args?: string[], options?: SpawnOptions): ChildProcess;

declare const _default: {
  VERSION: typeof VERSION;
  RELEASE_URL: typeof RELEASE_URL;
  findStudioBinary: typeof findStudioBinary;
  findServerBinary: typeof findServerBinary;
  launchMolForge: typeof launchMolForge;
  launchServer: typeof launchServer;
};

export default _default;
