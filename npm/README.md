# @yangdw2024/molforge

> CLI & Node.js launcher for **MolForge Studio 8.1.0** — Lightweight AI-assisted molecular workbench for 2D/3D structure prep, inspection & local engine orchestration (Electron + WebGPU + Rust).

## Instant Usage via `npx`

```bash
# Print CLI version
npx @yangdw2024/molforge --version

# Inspect detected desktop / server binaries and live API health
npx @yangdw2024/molforge --status

# Launch MolForge Studio desktop workstation (if installed locally)
npx @yangdw2024/molforge

# Launch native Rust HTTP core server (:18765)
npx @yangdw2024/molforge --server
```

## Binary Discovery

The wrapper searches:
1. `MOLFORGE_STUDIO_BIN` / `MOLFORGE_SERVER_BIN` environment overrides
2. Windows local installation (`%LOCALAPPDATA%\Programs\MolForge Studio\MolForge Studio.exe`)
3. Local workspace builds (`desktop/release/win-unpacked`, `desktop/resources/core`, `molforge-core/target/release`)
4. System `PATH`

Download official v8.1.0 Windows installer & portable builds:
https://github.com/yangdw2024/MolForge/releases/tag/v8.1.0

## License

Apache-2.0 — MolForge Team (yangdw2024).
