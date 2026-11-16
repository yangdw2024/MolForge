"""Stdio-to-desktop MCP forwarding with explicit local authentication."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path


def request_via_desktop(connection_path: str | Path, request: dict, timeout: float = 30.0) -> dict:
    path = Path(connection_path)
    connection = json.loads(path.read_text(encoding="utf-8"))
    if not connection.get("active") or connection.get("protocol") != "molforge-desktop-mcp-v1":
        raise RuntimeError("桌面 MCP 服务未启动，请先在 MolForge 工具菜单中启动")
    envelope = {"token": connection["token"], "request": request}
    with socket.create_connection((connection["host"], int(connection["port"])), timeout=timeout) as client:
        client.settimeout(timeout)
        client.sendall(json.dumps(envelope, ensure_ascii=False).encode("utf-8") + b"\n")
        reader = client.makefile("rb")
        line = reader.readline(8 * 1024 * 1024 + 1)
    if not line or len(line) > 8 * 1024 * 1024:
        raise RuntimeError("桌面 MCP 返回为空或消息过大")
    return json.loads(line.decode("utf-8"))


def run_desktop_stdio_loop(connection_path: str | Path):
    for line in sys.stdin:
        if not line.strip():
            continue
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            response = request_via_desktop(connection_path, request)
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
