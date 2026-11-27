import path from "node:path";

export const ALLOWED_READ_EXTENSIONS = new Set([
  ".mforge",
  ".pdb",
  ".xyz",
  ".mol",
  ".sdf",
  ".cif",
  ".mol2",
  ".log",
  ".fchk",
  ".wfn",
  ".wfx",
  ".molden",
  ".gjf",
  ".in",
  ".smi",
  ".csv",
  ".json",
]);

export const ALLOWED_WRITE_EXTENSIONS = new Set([
  ".mforge",
  ".pdb",
  ".xyz",
  ".mol",
  ".gjf",
  ".in",
  ".csv",
  ".json",
  ".md",
  ".svg",
]);

export function sanitizeFilePath(
  rawPath: unknown,
  allowedExtensions: Set<string> = ALLOWED_WRITE_EXTENSIONS
): { ok: true; resolved: string } | { ok: false; error: string } {
  if (typeof rawPath !== "string") {
    return { ok: false, error: "文件路径必须为字符串" };
  }
  const trimmed = rawPath.trim();
  if (!trimmed || trimmed.includes("\0")) {
    return { ok: false, error: "非法或空文件路径" };
  }
  if (!path.isAbsolute(trimmed)) {
    return { ok: false, error: "仅允许绝对路径操作" };
  }
  const parts = trimmed.split(/[\\/]+/);
  if (parts.includes("..")) {
    return { ok: false, error: "禁止路径穿越段 (..)" };
  }
  const resolved = path.resolve(trimmed);
  const lowerResolved = resolved.toLowerCase();
  if (
    lowerResolved.startsWith("c:\\windows") ||
    lowerResolved.startsWith("c:\\program files")
  ) {
    return { ok: false, error: "禁止写入受保护系统目录" };
  }
  const ext = path.extname(resolved).toLowerCase();
  if (!allowedExtensions.has(ext)) {
    return { ok: false, error: `不支持的扩展名: ${ext || "(无扩展名)"}` };
  }
  return { ok: true, resolved };
}

export function isAllowedExternalUrl(rawUrl: unknown): boolean {
  if (typeof rawUrl !== "string") return false;
  try {
    const parsed = new URL(rawUrl.trim());
    return parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function buildDesktopCsp(isDev: boolean): string {
  if (isDev) {
    return [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      "connect-src 'self' http://127.0.0.1:18765 http://127.0.0.1:5178 ws://127.0.0.1:5178",
      "object-src 'none'",
      "frame-ancestors 'none'",
    ].join("; ");
  }
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self' http://127.0.0.1:18765",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}
