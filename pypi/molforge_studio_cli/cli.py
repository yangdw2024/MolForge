"""CLI launcher and local HTTP core probe for MolForge Studio 8.1.0."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

__version__ = "8.2.0"
GITHUB_REPO = "yangdw2024/MolForge"
RELEASE_TAG = f"v{__version__}"
DEFAULT_SERVER_URL = "http://127.0.0.1:18765"


def _is_exec(path: Path | None) -> str | None:
    if path and path.is_file():
        return str(path.resolve())
    return None


def find_studio_binary() -> str | None:
    """Locate MolForge Studio desktop executable on this machine."""
    explicit = os.environ.get("MOLFORGE_STUDIO_BIN", "").strip()
    if explicit:
        return _is_exec(Path(explicit))

    exe_name = "MolForge Studio.exe" if os.name == "nt" else "molforge-studio"
    candidates: list[Path] = []
    if os.name == "nt":
        local_app = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        candidates.extend(
            [
                local_app / "Programs" / "MolForge Studio" / exe_name,
                local_app / "MolForge" / "bin" / f"MolForge-Studio-{__version__}-win-x64-portable.exe",
            ]
        )
    cwd = Path.cwd()
    candidates.extend(
        [
            cwd / "desktop" / "release" / "win-unpacked" / exe_name,
            cwd / "release" / "win-unpacked" / exe_name,
        ]
    )
    for cand in candidates:
        found = _is_exec(cand)
        if found:
            return found

    in_path = shutil.which(exe_name)
    return in_path


def find_server_binary() -> str | None:
    """Locate native Rust molforge-server binary on this machine."""
    explicit = os.environ.get("MOLFORGE_SERVER_BIN", "").strip()
    if explicit:
        return _is_exec(Path(explicit))

    exe_name = "molforge-server.exe" if os.name == "nt" else "molforge-server"
    cwd = Path.cwd()
    candidates = [
        cwd / "desktop" / "resources" / "core" / exe_name,
        cwd / "molforge-core" / "target" / "release" / exe_name,
        cwd / "target" / "release" / exe_name,
    ]
    if os.name == "nt":
        local_app = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        candidates.extend(
            [
                local_app / "Programs" / "MolForge Studio" / "resources" / "core" / exe_name,
                local_app / "MolForge" / "bin" / exe_name,
            ]
        )
    for cand in candidates:
        found = _is_exec(cand)
        if found:
            return found

    return shutil.which(exe_name)


def server_health(base_url: str = DEFAULT_SERVER_URL, timeout: float = 2.0) -> dict[str, Any] | None:
    """Query `/api/health` on a running molforge-server instance."""
    url = base_url.rstrip("/") + "/api/health"
    req = urllib.request.Request(url, headers={"User-Agent": f"molforge-studio/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def download_release_asset(
    dest_dir: Path | None = None,
    asset_name: str = f"MolForge-Studio-{__version__}-win-x64-portable.exe",
) -> Path:
    """Download an official release asset from GitHub Releases."""
    target_dir = dest_dir or (Path.home() / "AppData" / "Local" / "MolForge" / "bin")
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / asset_name
    url = f"https://github.com/{GITHUB_REPO}/releases/download/{RELEASE_TAG}/{asset_name}"
    print(f"Downloading {url} -> {out_path} ...")
    req = urllib.request.Request(url, headers={"User-Agent": f"molforge-studio/{__version__}"})
    with urllib.request.urlopen(req, timeout=120) as resp, out_path.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="molforge",
        description=f"MolForge Studio {__version__} launcher & HTTP core helper",
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("--status", action="store_true", help="Show detected binaries and server health")
    parser.add_argument("--server", action="store_true", help="Launch native Rust molforge-server")
    parser.add_argument("--download", action="store_true", help="Download official Windows portable binary from GitHub Releases")
    parser.add_argument("--port", type=int, default=18765, help="Server port (when using --server)")
    args, extra = parser.parse_known_args(argv)

    if args.version:
        print(f"molforge-studio {__version__}")
        return 0

    if args.status:
        studio = find_studio_binary()
        server = find_server_binary()
        health = server_health(f"http://127.0.0.1:{args.port}")
        print(json.dumps({
            "version": __version__,
            "studio_bin": studio,
            "server_bin": server,
            "server_health": health,
            "releases": f"https://github.com/{GITHUB_REPO}/releases/tag/{RELEASE_TAG}",
        }, indent=2, ensure_ascii=False))
        return 0

    if args.download:
        try:
            saved = download_release_asset()
            print(f"Saved: {saved}")
            return 0
        except urllib.error.URLError as exc:
            print(f"Download failed: {exc}", file=sys.stderr)
            return 1

    if args.server:
        srv = find_server_binary()
        if not srv:
            print(
                f"molforge-server binary not found. Set MOLFORGE_SERVER_BIN or download from:\n"
                f"  https://github.com/{GITHUB_REPO}/releases/tag/{RELEASE_TAG}",
                file=sys.stderr,
            )
            return 1
        env = dict(os.environ)
        env.setdefault("MOLFORGE_PORT", str(args.port))
        return subprocess.call([srv, *extra], env=env)

    studio = find_studio_binary()
    if studio:
        return subprocess.call([studio, *extra])

    print(
        f"MolForge Studio desktop binary was not found locally.\n"
        f"Download v{__version__} installer or portable app from:\n"
        f"  https://github.com/{GITHUB_REPO}/releases/tag/{RELEASE_TAG}\n"
        f"Or run `molforge --download` on Windows.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
