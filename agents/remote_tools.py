"""
Remote Control Module - Tools for remote PC management via WebSocket/HTTP.
"""
import asyncio
import base64
import json
import os
import psutil
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base import Tool
from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)


class RemoteControlServer:
    """Manages remote control sessions and WebSocket connections."""

    def __init__(self):
        self.settings = get_settings()
        self.active_sessions: Dict[str, Dict] = {}
        self.websocket_clients: set = set()
        self._server_task: Optional[asyncio.Task] = None

    async def register_client(self, websocket, session_id: str):
        """Register a new WebSocket client."""
        self.websocket_clients.add(websocket)
        self.active_sessions[session_id] = {
            "websocket": websocket,
            "connected_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
        }
        logger.info(f"Remote client connected: {session_id}")

    async def unregister_client(self, websocket, session_id: str):
        """Unregister a WebSocket client."""
        self.websocket_clients.discard(websocket)
        self.active_sessions.pop(session_id, None)
        logger.info(f"Remote client disconnected: {session_id}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self.websocket_clients:
            return
        data = json.dumps(message)
        disconnected = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            self.websocket_clients.discard(ws)

    def get_status(self) -> dict:
        """Get server status."""
        return {
            "active_sessions": len(self.active_sessions),
            "websocket_clients": len(self.websocket_clients),
            "sessions": [
                {
                    "id": sid,
                    "connected_at": s["connected_at"].isoformat(),
                    "last_activity": s["last_activity"].isoformat(),
                }
                for sid, s in self.active_sessions.items()
            ]
        }


# Global instance
_remote_server: Optional[RemoteControlServer] = None


def get_remote_server() -> RemoteControlServer:
    global _remote_server
    if _remote_server is None:
        _remote_server = RemoteControlServer()
    return _remote_server


class FileManagerTool(Tool):
    """File management operations for remote control."""

    @property
    def name(self) -> str:
        return "remote_file_manager"

    @property
    def description(self) -> str:
        return "Remote file operations: list, read, write, delete, upload, download, search."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "read", "write", "delete", "mkdir", "copy", "move", "search", "info", "download", "upload"],
                    "description": "Action to perform"
                },
                "path": {"type": "string", "description": "File/directory path"},
                "destination": {"type": "string", "description": "Destination path for copy/move"},
                "content": {"type": "string", "description": "Content to write (base64 for binary)"},
                "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
                "recursive": {"type": "boolean", "description": "Recursive operation", "default": False},
                "pattern": {"type": "string", "description": "Search pattern (glob)"},
            },
            "required": ["action", "path"]
        }

    async def execute(self, action: str, path: str, **kwargs) -> str:
        try:
            p = Path(path).resolve()

            if action == "list":
                if not p.exists():
                    return f"❌ Path not found: {path}"
                if not p.is_dir():
                    return f"❌ Not a directory: {path}"

                items = []
                for item in p.iterdir():
                    stat = item.stat()
                    items.append({
                        "name": item.name,
                        "path": str(item),
                        "type": "dir" if item.is_dir() else "file",
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                return json.dumps({"path": str(p), "items": items}, ensure_ascii=False)

            elif action == "read":
                if not p.exists() or not p.is_file():
                    return f"❌ File not found: {path}"
                encoding = kwargs.get("encoding", "utf-8")
                try:
                    content = p.read_text(encoding=encoding)
                except UnicodeDecodeError:
                    # Binary file - return base64
                    content = base64.b64encode(p.read_bytes()).decode()
                    return json.dumps({
                        "path": str(p),
                        "content": content,
                        "encoding": "base64",
                        "size": p.stat().st_size
                    }, ensure_ascii=False)
                return json.dumps({
                    "path": str(p),
                    "content": content,
                    "encoding": encoding,
                    "size": p.stat().st_size
                }, ensure_ascii=False)

            elif action == "write":
                content = kwargs.get("content", "")
                encoding = kwargs.get("encoding", "utf-8")
                p.parent.mkdir(parents=True, exist_ok=True)

                # Check if base64
                try:
                    decoded = base64.b64decode(content)
                    p.write_bytes(decoded)
                except Exception:
                    p.write_text(content, encoding=encoding)
                return f"✅ Written to {path} ({p.stat().st_size} bytes)"

            elif action == "delete":
                if not p.exists():
                    return f"❌ Not found: {path}"
                if p.is_dir():
                    shutil.rmtree(p) if kwargs.get("recursive") else p.rmdir()
                else:
                    p.unlink()
                return f"✅ Deleted: {path}"

            elif action == "mkdir":
                p.mkdir(parents=True, exist_ok=True)
                return f"✅ Created directory: {path}"

            elif action == "copy":
                dest = Path(kwargs.get("destination", "")).resolve()
                if not dest:
                    return "❌ Destination required"
                if p.is_dir():
                    shutil.copytree(p, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(p, dest)
                return f"✅ Copied to {destination}"

            elif action == "move":
                dest = Path(kwargs.get("destination", "")).resolve()
                if not dest:
                    return "❌ Destination required"
                shutil.move(str(p), str(dest))
                return f"✅ Moved to {destination}"

            elif action == "search":
                pattern = kwargs.get("pattern", "*")
                recursive = kwargs.get("recursive", False)
                results = []
                if p.is_dir():
                    glob_method = p.rglob if recursive else p.glob
                    for item in glob_method(pattern):
                        results.append({"name": item.name, "path": str(item), "type": "dir" if item.is_dir() else "file"})
                return json.dumps({"path": str(p), "pattern": pattern, "results": results}, ensure_ascii=False)

            elif action == "info":
                if not p.exists():
                    return f"❌ Not found: {path}"
                stat = p.stat()
                return json.dumps({
                    "path": str(p),
                    "name": p.name,
                    "type": "dir" if p.is_dir() else "file",
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "permissions": oct(stat.st_mode)[-3:],
                }, ensure_ascii=False)

            elif action == "upload":
                # Receive base64 content and save
                content = kwargs.get("content", "")
                try:
                    decoded = base64.b64decode(content)
                    p.write_bytes(decoded)
                except Exception:
                    p.write_text(content)
                return f"✅ Uploaded to {path} ({p.stat().st_size} bytes)"

            elif action == "download":
                # Return file as base64
                if not p.is_file():
                    return f"❌ Not a file: {path}"
                content = base64.b64encode(p.read_bytes()).decode()
                return json.dumps({
                    "path": str(p),
                    "content": content,
                    "encoding": "base64",
                    "filename": p.name,
                    "size": p.stat().st_size
                }, ensure_ascii=False)

            else:
                return f"❌ Unknown action: {action}"

        except Exception as e:
            logger.error(f"FileManager error: {e}")
            return f"❌ Error: {e}"


class ProcessManagerTool(Tool):
    """Process management for remote control."""

    @property
    def name(self) -> str:
        return "remote_process_manager"

    @property
    def description(self) -> str:
        return "Process management: list, kill, start, info, resource usage."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "kill", "start", "info", "cpu", "memory", "tree"],
                    "description": "Action to perform"
                },
                "pid": {"type": "integer", "description": "Process ID"},
                "name": {"type": "string", "description": "Process name filter"},
                "command": {"type": "string", "description": "Command to start"},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments"},
                "limit": {"type": "integer", "description": "Max results", "default": 50},
            },
            "required": ["action"]
        }

    async def execute(self, action: str, **kwargs) -> str:
        try:
            if action == "list":
                limit = kwargs.get("limit", 50)
                name_filter = kwargs.get("name", "").lower()
                processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'username', 'create_time', 'status']):
                    try:
                        info = proc.info
                        if name_filter and name_filter not in (info.get('name') or '').lower():
                            continue
                        info['create_time'] = datetime.fromtimestamp(info['create_time']).isoformat() if info.get('create_time') else None
                        processes.append(info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                processes.sort(key=lambda x: x.get('cpu_percent', 0) or 0, reverse=True)
                return json.dumps({"count": len(processes), "processes": processes[:limit]}, ensure_ascii=False)

            elif action == "info":
                pid = kwargs.get("pid")
                if not pid:
                    return "❌ PID required"
                try:
                    proc = psutil.Process(pid)
                    info = proc.as_dict(attrs=['pid', 'name', 'exe', 'cmdline', 'cwd', 'username', 'create_time', 'cpu_percent', 'memory_percent', 'memory_info', 'status', 'threads', 'connections'])
                    info['create_time'] = datetime.fromtimestamp(info['create_time']).isoformat()
                    if info.get('memory_info'):
                        info['memory_info'] = {
                            'rss': info['memory_info'].rss,
                            'vms': info['memory_info'].vms,
                        }
                    return json.dumps(info, ensure_ascii=False, default=str)
                except psutil.NoSuchProcess:
                    return f"❌ Process {pid} not found"

            elif action == "kill":
                pid = kwargs.get("pid")
                force = kwargs.get("force", False)
                if not pid:
                    return "❌ PID required"
                try:
                    proc = psutil.Process(pid)
                    if force:
                        proc.kill()
                    else:
                        proc.terminate()
                    proc.wait(timeout=5)
                    return f"✅ Process {pid} {'killed' if force else 'terminated'}"
                except psutil.NoSuchProcess:
                    return f"❌ Process {pid} not found"
                except psutil.AccessDenied:
                    return f"❌ Access denied to kill {pid}"

            elif action == "start":
                cmd = kwargs.get("command")
                args = kwargs.get("args", [])
                if not cmd:
                    return "❌ Command required"
                try:
                    full_cmd = [cmd] + args
                    proc = subprocess.Popen(full_cmd, start_new_session=True)
                    return f"✅ Started PID {proc.pid}: {' '.join(full_cmd)}"
                except Exception as e:
                    return f"❌ Failed to start: {e}"

            elif action == "cpu":
                # System-wide CPU
                return json.dumps({
                    "per_cpu": psutil.cpu_percent(percpu=True),
                    "total": psutil.cpu_percent(),
                    "count_logical": psutil.cpu_count(),
                    "count_physical": psutil.cpu_count(logical=False),
                    "freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                    "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None,
                }, ensure_ascii=False)

            elif action == "memory":
                mem = psutil.virtual_memory()
                swap = psutil.swap_memory()
                return json.dumps({
                    "total": mem.total,
                    "available": mem.available,
                    "used": mem.used,
                    "percent": mem.percent,
                    "swap_total": swap.total,
                    "swap_used": swap.used,
                    "swap_percent": swap.percent,
                }, ensure_ascii=False)

            elif action == "tree":
                pid = kwargs.get("pid")
                if not pid:
                    return "❌ PID required"
                try:
                    proc = psutil.Process(pid)
                    tree = self._build_process_tree(proc)
                    return json.dumps(tree, ensure_ascii=False)
                except psutil.NoSuchProcess:
                    return f"❌ Process {pid} not found"

            else:
                return f"❌ Unknown action: {action}"

        except Exception as e:
            logger.error(f"ProcessManager error: {e}")
            return f"❌ Error: {e}"

    def _build_process_tree(self, proc: psutil.Process, depth: int = 0) -> dict:
        """Build process tree recursively."""
        try:
            info = {
                "pid": proc.pid,
                "name": proc.name(),
                "cpu_percent": proc.cpu_percent(),
                "memory_percent": proc.memory_percent(),
                "children": []
            }
            for child in proc.children(recursive=False):
                info["children"].append(self._build_process_tree(child, depth + 1))
            return info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"pid": proc.pid, "name": "?", "error": "access denied"}


class SystemControlTool(Tool):
    """System-level control: shutdown, restart, sleep, lock, clipboard, etc."""

    @property
    def name(self) -> str:
        return "remote_system_control"

    @property
    def description(self) -> str:
        return "System control: shutdown, restart, sleep, lock, clipboard, notifications, volume, brightness."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["shutdown", "restart", "sleep", "hibernate", "lock", "logoff",
                             "clipboard_get", "clipboard_set", "notify", "volume_get", "volume_set",
                             "brightness_get", "brightness_set", "screenshot", "wifi_list", "wifi_connect"],
                    "description": "Action to perform"
                },
                "text": {"type": "string", "description": "Text for clipboard/notification"},
                "title": {"type": "string", "description": "Notification title"},
                "volume": {"type": "number", "description": "Volume level 0-100"},
                "brightness": {"type": "number", "description": "Brightness 0-100"},
                "ssid": {"type": "string", "description": "WiFi SSID"},
                "password": {"type": "string", "description": "WiFi password"},
                "delay": {"type": "integer", "description": "Delay in seconds", "default": 0},
            },
            "required": ["action"]
        }

    async def execute(self, action: str, **kwargs) -> str:
        try:
            delay = kwargs.get("delay", 0)
            if delay:
                await asyncio.sleep(delay)

            if action == "shutdown":
                os.system("shutdown /s /t 0" if sys.platform == "win32" else "shutdown -h now")
                return "🔴 Shutting down..."

            elif action == "restart":
                os.system("shutdown /r /t 0" if sys.platform == "win32" else "shutdown -r now")
                return "🔄 Restarting..."

            elif action == "sleep":
                if sys.platform == "win32":
                    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
                else:
                    os.system("systemctl suspend")
                return "😴 Sleeping..."

            elif action == "hibernate":
                if sys.platform == "win32":
                    os.system("shutdown /h")
                else:
                    os.system("systemctl hibernate")
                return "💤 Hibernating..."

            elif action == "lock":
                if sys.platform == "win32":
                    os.system("rundll32.exe user32.dll,LockWorkStation")
                else:
                    os.system("gnome-screensaver-command -l" if shutil.which("gnome-screensaver-command") else "dm-tool lock")
                return "🔒 Locked"

            elif action == "logoff":
                if sys.platform == "win32":
                    os.system("shutdown /l")
                else:
                    os.system("gnome-session-quit --logout --no-prompt")
                return "👋 Logging off..."

            elif action == "clipboard_get":
                try:
                    import pyperclip
                    text = pyperclip.paste()
                    return json.dumps({"text": text}, ensure_ascii=False)
                except Exception as e:
                    return f"❌ Clipboard error: {e}"

            elif action == "clipboard_set":
                text = kwargs.get("text", "")
                try:
                    import pyperclip
                    pyperclip.copy(text)
                    return "✅ Clipboard updated"
                except Exception as e:
                    return f"❌ Clipboard error: {e}"

            elif action == "notify":
                title = kwargs.get("title", "Everlay Remote")
                text = kwargs.get("text", "")
                try:
                    if sys.platform == "win32":
                        from win10toast import ToastNotifier
                        ToastNotifier().show_toast(title, text, duration=5)
                    else:
                        os.system(f'notify-send "{title}" "{text}"')
                    return "✅ Notification sent"
                except Exception as e:
                    return f"❌ Notification error: {e}"

            elif action == "volume_get":
                try:
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    from comtypes import CLSCTX_ALL
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = interface.QueryInterface(IAudioEndpointVolume)
                    return json.dumps({"volume": round(volume.GetMasterVolumeLevelScalar() * 100), "muted": volume.GetMute()})
                except Exception as e:
                    return f"❌ Volume error: {e}"

            elif action == "volume_set":
                vol = kwargs.get("volume", 50)
                try:
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    from comtypes import CLSCTX_ALL
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = interface.QueryInterface(IAudioEndpointVolume)
                    volume.SetMasterVolumeLevelScalar(vol / 100, None)
                    return f"🔊 Volume set to {vol}%"
                except Exception as e:
                    return f"❌ Volume error: {e}"

            elif action == "screenshot":
                try:
                    import pyautogui
                    img = pyautogui.screenshot()
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    return json.dumps({"image": b64, "format": "png", "encoding": "base64"}, ensure_ascii=False)
                except Exception as e:
                    return f"❌ Screenshot error: {e}"

            elif action == "wifi_list":
                if sys.platform == "win32":
                    result = subprocess.run(["netsh", "wlan", "show", "networks", "mode=bssid"], capture_output=True, text=True)
                    return result.stdout
                else:
                    result = subprocess.run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi"], capture_output=True, text=True)
                    return result.stdout

            elif action == "wifi_connect":
                ssid = kwargs.get("ssid")
                password = kwargs.get("password", "")
                if not ssid:
                    return "❌ SSID required"
                if sys.platform == "win32":
                    cmd = f'netsh wlan connect name="{ssid}"' + (f' key="{password}"' if password else '')
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    return result.stdout or result.stderr
                else:
                    result = subprocess.run(["nmcli", "dev", "wifi", "connect", ssid, "password", password], capture_output=True, text=True)
                    return result.stdout or result.stderr

            else:
                return f"❌ Unknown action: {action}"

        except Exception as e:
            logger.error(f"SystemControl error: {e}")
            return f"❌ Error: {e}"


class RemoteControlTool(Tool):
    """Main remote control tool - aggregates all sub-tools."""

    @property
    def name(self) -> str:
        return "remote_control"

    @property
    def description(self) -> str:
        return "Complete remote PC control: files, processes, system, clipboard, screen, network."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "enum": ["files", "processes", "system", "status"],
                    "description": "Module to use"
                },
                "action": {"type": "string", "description": "Action within module"},
                "params": {"type": "object", "description": "Action parameters"},
            },
            "required": ["module", "action"]
        }

    def __init__(self):
        self.files = FileManagerTool()
        self.processes = ProcessManagerTool()
        self.system = SystemControlTool()

    async def execute(self, module: str, action: str, params: dict = None) -> str:
        params = params or {}
        try:
            if module == "files":
                return await self.files.execute(action, **params)
            elif module == "processes":
                return await self.processes.execute(action, **params)
            elif module == "system":
                return await self.system.execute(action, **params)
            elif module == "status":
                server = get_remote_server()
                return json.dumps(server.get_status(), ensure_ascii=False)
            else:
                return f"❌ Unknown module: {module}"
        except Exception as e:
            logger.error(f"RemoteControl error: {e}")
            return f"❌ Error: {e}"


# Export all tools
REMOTE_TOOLS = [
    RemoteControlTool(),
    FileManagerTool(),
    ProcessManagerTool(),
    SystemControlTool(),
]


def get_remote_tools() -> List[Tool]:
    return REMOTE_TOOLS