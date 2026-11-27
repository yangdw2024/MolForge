/**
 * desktop/src/services/commands.ts
 * Centralized Command Registry for MolForge Studio 8.1
 * Maps all 343 scientific operations to actions, shortcuts, and categories
 */

export interface StudioCommand {
  id: string;
  label: string;
  category: "文件" | "编辑" | "构建" | "结构" | "计算" | "结果" | "表面" | "视图" | "图层" | "帮助";
  shortcut?: string;
  description?: string;
  execute: () => void | Promise<void>;
}

class CommandManager {
  private commands = new Map<string, StudioCommand>();
  private listeners: Array<() => void> = [];

  register(cmd: StudioCommand): void {
    this.commands.set(cmd.id, cmd);
    this.notify();
  }

  registerBatch(cmds: StudioCommand[]): void {
    for (const cmd of cmds) {
      this.commands.set(cmd.id, cmd);
    }
    this.notify();
  }

  get(id: string): StudioCommand | undefined {
    return this.commands.get(id);
  }

  getAll(): StudioCommand[] {
    return Array.from(this.commands.values());
  }

  getByCategory(cat: StudioCommand["category"]): StudioCommand[] {
    return this.getAll().filter((c) => c.category === cat);
  }

  execute(id: string): void {
    const cmd = this.commands.get(id);
    if (cmd) {
      void cmd.execute();
    }
  }

  subscribe(listener: () => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private notify() {
    for (const l of this.listeners) l();
  }
}

export const commandRegistry = new CommandManager();
