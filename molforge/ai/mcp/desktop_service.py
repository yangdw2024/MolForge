"""Authenticated localhost MCP service running in the desktop's Qt main thread."""
from __future__ import annotations

import hmac
import json
import secrets
from pathlib import Path

from PyQt6.QtCore import QObject
from PyQt6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

from ...runtime import data_dir
from .mcp_server import MolForgeMCPServer


class DesktopMCPService(QObject):
    """Expose the *current* desktop document to local MCP clients.

    Every request constructs a lightweight protocol handler around the latest
    document/command-bus references.  QTcpServer delivers requests on the GUI
    thread, so command listeners and VTK updates never run on a socket worker.
    """

    MAX_MESSAGE_BYTES = 8 * 1024 * 1024

    def __init__(self, document_provider, command_bus_provider, connection_path=None, parent=None):
        super().__init__(parent)
        self._document_provider = document_provider
        self._command_bus_provider = command_bus_provider
        self.connection_path = Path(connection_path) if connection_path else data_dir() / "mcp" / "desktop.json"
        self._tcp = QTcpServer(self)
        self._tcp.newConnection.connect(self._accept_connections)
        self._clients: set[QTcpSocket] = set()
        self._buffers: dict[QTcpSocket, bytes] = {}
        self._token = ""

    @property
    def is_active(self) -> bool:
        return self._tcp.isListening()

    @property
    def port(self) -> int:
        return int(self._tcp.serverPort())

    def start(self) -> dict:
        if self.is_active:
            return self.connection_info(include_token=True)
        self._token = secrets.token_urlsafe(32)
        if not self._tcp.listen(QHostAddress.SpecialAddress.LocalHost, 0):
            raise RuntimeError(f"无法监听本机 MCP 端口: {self._tcp.errorString()}")
        self._write_connection_file(active=True)
        return self.connection_info(include_token=True)

    def stop(self):
        for client in list(self._clients):
            client.disconnectFromHost()
            client.close()
        self._clients.clear()
        self._buffers.clear()
        self._tcp.close()
        self._write_connection_file(active=False)

    def connection_info(self, include_token: bool = False) -> dict:
        info = {
            "active": self.is_active,
            "protocol": "molforge-desktop-mcp-v1",
            "host": "127.0.0.1",
            "port": self.port,
        }
        if include_token:
            info["token"] = self._token
        return info

    def _write_connection_file(self, active: bool):
        self.connection_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.connection_info(include_token=active)
        temporary = self.connection_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.connection_path)

    def _accept_connections(self):
        while self._tcp.hasPendingConnections():
            client = self._tcp.nextPendingConnection()
            self._clients.add(client)
            self._buffers[client] = b""
            client.readyRead.connect(lambda c=client: self._read_client(c))
            client.disconnected.connect(lambda c=client: self._discard_client(c))

    def _discard_client(self, client):
        self._clients.discard(client)
        self._buffers.pop(client, None)
        client.deleteLater()

    def _send(self, client, response):
        payload = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
        client.write(payload)
        client.flush()

    def _read_client(self, client):
        self._buffers[client] = self._buffers.get(client, b"") + bytes(client.readAll())
        if len(self._buffers[client]) > self.MAX_MESSAGE_BYTES:
            self._send(client, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "MCP message too large"}})
            client.disconnectFromHost()
            return
        while b"\n" in self._buffers.get(client, b""):
            raw, self._buffers[client] = self._buffers[client].split(b"\n", 1)
            request_id = None
            try:
                envelope = json.loads(raw.decode("utf-8"))
                token = str(envelope.get("token", ""))
                if not hmac.compare_digest(token, self._token):
                    raise PermissionError("invalid desktop MCP token")
                request = envelope.get("request")
                if not isinstance(request, dict):
                    raise ValueError("missing JSON-RPC request")
                request_id = request.get("id")
                handler = MolForgeMCPServer(self._document_provider(), self._command_bus_provider())
                response = handler.handle_request(request)
            except Exception as exc:
                response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": str(exc)}}
            self._send(client, response)
