import { describe, expect, it } from "vitest";
import {
  ALLOWED_READ_EXTENSIONS,
  ALLOWED_WRITE_EXTENSIONS,
  buildDesktopCsp,
  isAllowedExternalUrl,
  sanitizeFilePath,
} from "../electron/security";

describe("Electron IPC & File Security Guards", () => {
  it("accepts clean absolute workspace paths with whitelisted extensions", () => {
    const res = sanitizeFilePath("E:\\YDW\\Projects\\molecule.mforge", ALLOWED_WRITE_EXTENSIONS);
    expect(res.ok).toBe(true);
    const readRes = sanitizeFilePath("E:\\YDW\\test_wsl\\ydw-PM6-ClFFCl.pdb", ALLOWED_READ_EXTENSIONS);
    expect(readRes.ok).toBe(true);
  });

  it("blocks path traversal, relative paths, null bytes, and protected system folders", () => {
    expect(sanitizeFilePath("relative/path.mforge").ok).toBe(false);
    expect(sanitizeFilePath("E:\\YDW\\..\\evil.mforge").ok).toBe(false);
    expect(sanitizeFilePath("E:\\YDW\\bad\0file.mforge").ok).toBe(false);
    expect(sanitizeFilePath("C:\\Windows\\System32\\payload.mforge").ok).toBe(false);
    expect(sanitizeFilePath("C:\\Program Files\\test\\out.pdb").ok).toBe(false);
  });

  it("blocks dangerous non-scientific file extensions", () => {
    expect(sanitizeFilePath("E:\\YDW\\bad.exe").ok).toBe(false);
    expect(sanitizeFilePath("E:\\YDW\\bad.bat").ok).toBe(false);
    expect(sanitizeFilePath("E:\\YDW\\bad.ps1").ok).toBe(false);
  });

  it("strictly validates external URLs to HTTPS only", () => {
    expect(isAllowedExternalUrl("https://github.com/yangdw2024/MolForge")).toBe(true);
    expect(isAllowedExternalUrl("http://127.0.0.1:8045")).toBe(false);
    expect(isAllowedExternalUrl("file:///C:/Windows/System32/calc.exe")).toBe(false);
    expect(isAllowedExternalUrl("javascript:alert(1)")).toBe(false);
  });

  it("generates locked-down production CSP", () => {
    const csp = buildDesktopCsp(false);
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("http://127.0.0.1:18765");
    expect(csp).not.toContain("'unsafe-eval'");
  });
});
