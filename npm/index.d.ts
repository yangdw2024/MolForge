import { ChildProcess, SpawnOptions } from 'node:child_process';

export declare function launchMolForge(
  args?: string[],
  options?: SpawnOptions
): ChildProcess;

declare const _default: {
  launchMolForge: typeof launchMolForge;
};

export default _default;
