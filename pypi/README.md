# MolForge Studio (`molforge-studio` 8.1.0)

Lightweight Python launcher, binary fetcher, and local HTTP core helper for **MolForge Studio 8.1.0** — a lightweight molecular workbench for 2D/3D structure prep, inspection & local engine orchestration.

## Installation

```bash
pip install -U molforge-studio
```

## CLI Usage

```bash
# Show detected MolForge Studio / molforge-server binaries and local server status
molforge --status

# Launch MolForge Studio desktop workstation (if installed locally)
molforge

# Launch headless Rust HTTP core server (:18765)
molforge --server

# Download official v8.1.0 Windows portable/installer assets from GitHub Releases
molforge --download
```

## Python API

```python
from molforge_studio_cli import find_studio_binary, find_server_binary, server_health

print("Studio:", find_studio_binary())
print("Server:", find_server_binary())
print("Health:", server_health())
```

## Links

- GitHub Repository & Releases: https://github.com/yangdw2024/MolForge/releases/tag/v8.1.0
- npm CLI Wrapper: https://www.npmjs.com/package/@yangdw2024/molforge
