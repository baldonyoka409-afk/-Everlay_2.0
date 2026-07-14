"""
Built-in tools for agents.
"""
import asyncio
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base import Tool

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class FileReadTool(Tool):
    """Read file contents."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read"},
                "encoding": {"type": "string", "description": "File encoding", "default": "utf-8"},
            },
            "required": ["path"],
        }

    async def execute(self, path: str, encoding: str = "utf-8") -> str:
        try:
            file_path = Path(path).resolve()
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            content = file_path.read_text(encoding=encoding)
            return content
        except Exception as e:
            return f"Error reading file: {e}"


class FileWriteTool(Tool):
    """Write file contents."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to write"},
                "content": {"type": "string", "description": "Content to write"},
                "encoding": {"type": "string", "description": "File encoding", "default": "utf-8"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, encoding: str = "utf-8") -> str:
        try:
            file_path = Path(path).resolve()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding=encoding)
            return f"Successfully wrote {len(content)} characters to {path}"
        except Exception as e:
            return f"Error writing file: {e}"


class FileListTool(Tool):
    """List files in a directory."""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "List files and directories in a given path."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
                "pattern": {"type": "string", "description": "Glob pattern", "default": "**/*"},
            },
            "required": [],
        }

    async def execute(self, path: str = ".", pattern: str = "**/*") -> str:
        try:
            dir_path = Path(path).resolve()
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"

            files = []
            for item in dir_path.rglob(pattern):
                rel = item.relative_to(dir_path)
                if item.is_file():
                    files.append(f"📄 {rel}")
                else:
                    files.append(f"📁 {rel}/")

            return "\n".join(files) if files else "No files found"
        except Exception as e:
            return f"Error listing files: {e}"


class ShellTool(Tool):
    """Execute shell commands."""

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute a shell command and return output."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to execute"},
                "cwd": {"type": "string", "description": "Working directory", "default": "."},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["command"],
        }

    async def execute(self, command: str, cwd: str = ".", timeout: int = 30) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return f"Error: Command timed out after {timeout}s"

            result = []
            if stdout:
                result.append(f"STDOUT:\n{stdout.decode('utf-8', errors='replace')}")
            if stderr:
                result.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")
            result.append(f"Exit code: {proc.returncode}")

            return "\n".join(result)
        except Exception as e:
            return f"Error executing command: {e}"


class PythonTool(Tool):
    """Execute Python code."""

    @property
    def name(self) -> str:
        return "python"

    @property
    def description(self) -> str:
        return "Execute Python code and return output."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["code"],
        }

    async def execute(self, code: str, timeout: int = 30) -> str:
        try:
            # Create a temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                temp_path = f.name

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, temp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.communicate()
                    return f"Error: Execution timed out after {timeout}s"

                result = []
                if stdout:
                    result.append(stdout.decode('utf-8', errors='replace'))
                if stderr:
                    result.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")
                if proc.returncode != 0:
                    result.append(f"Exit code: {proc.returncode}")

                return "\n".join(result) if result else "Executed successfully (no output)"
            finally:
                os.unlink(temp_path)
        except Exception as e:
            return f"Error executing Python: {e}"


class CodeInterpreterTool(Tool):
    """
    Persistent Python interpreter with state (variables, imports, functions persist between calls).
    Like Open Interpreter - maintains a Jupyter-like kernel session.
    """

    _kernel = None  # Class-level kernel to persist across instances

    @property
    def name(self) -> str:
        return "code_interpreter"

    @property
    def description(self) -> str:
        return "Execute Python code with persistent state (variables, imports, functions persist between calls). Like a Jupyter notebook."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "reset": {"type": "boolean", "description": "Reset kernel state", "default": False},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
            },
            "required": ["code"],
        }

    def _get_kernel(self):
        """Get or create persistent kernel."""
        if CodeInterpreterTool._kernel is None:
            CodeInterpreterTool._kernel = PersistentKernel()
        return CodeInterpreterTool._kernel

    async def execute(self, code: str, reset: bool = False, timeout: int = 60) -> str:
        kernel = self._get_kernel()
        if reset:
            kernel.reset()
        return await kernel.execute(code, timeout)


class PersistentKernel:
    """Persistent Python kernel using subprocess with stdin/stdout."""

    def __init__(self):
        self._process = None
        self._initialized = False

    async def _ensure_started(self):
        """Start the kernel process if not running."""
        if self._process is None or self._process.returncode is not None:
            import sys
            self._process = await asyncio.create_subprocess_exec(
                sys.executable, "-u", "-c",
                # Kernel code that reads from stdin and executes
                """
import sys, json, traceback, builtins

# Setup namespace
namespace = {'__builtins__': builtins}

def execute(code):
    try:
        # Try to compile as expression first (for return values)
        try:
            compiled = compile(code, '<input>', 'eval')
            result = eval(compiled, namespace, namespace)
            if result is not None:
                return {'type': 'result', 'value': repr(result)}
        except SyntaxError:
            pass

        # Execute as statements
        compiled = compile(code, '<input>', 'exec')
        exec(compiled, namespace, namespace)
        return {'type': 'ok'}
    except Exception as e:
        return {'type': 'error', 'value': traceback.format_exc()}

# Main loop
print('KERNEL_READY', flush=True)
for line in sys.stdin:
    line = line.rstrip('\\n')
    if line == '__KERNEL_RESET__':
        namespace.clear()
        namespace['__builtins__'] = builtins
        print('KERNEL_RESET', flush=True)
        continue
    if line == '__KERNEL_EXIT__':
        break

    # Read multi-line input
    code = line
    while True:
        try:
            next_line = next(sys.stdin).rstrip('\\n')
            if next_line == '__KERNEL_END__':
                break
            code += '\\n' + next_line
        except StopIteration:
            break

    result = execute(code)
    print('__KERNEL_RESULT__' + json.dumps(result, ensure_ascii=False), flush=True)
""",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._initialized = False

        if not self._initialized:
            # Wait for ready signal
            line = await self._process.stdout.readline()
            if b'KERNEL_READY' in line:
                self._initialized = True

    async def execute(self, code: str, timeout: int = 60) -> str:
        await self._ensure_started()

        # Send code
        code_lines = code.split('\n')
        for line in code_lines:
            self._process.stdin.write((line + '\n').encode())
        self._process.stdin.write(b'__KERNEL_END__\n')
        await self._process.stdin.drain()

        # Read result
        try:
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=timeout)
            line = line.decode('utf-8', errors='replace').strip()
            if line.startswith('__KERNEL_RESULT__'):
                import json
                result = json.loads(line[15:])
                if result['type'] == 'result':
                    return result['value']
                elif result['type'] == 'ok':
                    return "✓ Executed successfully"
                elif result['type'] == 'error':
                    return f"Error:\n{result['value']}"
            return f"Unexpected response: {line}"
        except asyncio.TimeoutError:
            return f"Error: Timeout after {timeout}s"

    def reset(self):
        """Reset kernel state."""
        if self._process and self._process.returncode is None:
            self._process.stdin.write(b'__KERNEL_RESET__\n')
            # Note: we don't await here since it's sync
        self._initialized = False

    async def close(self):
        """Close kernel."""
        if self._process and self._process.returncode is None:
            self._process.stdin.write(b'__KERNEL_EXIT__\n')
            await self._process.stdin.drain()
            await self._process.wait()


class ResourceMonitorTool(Tool):
    """System resource monitoring (CPU, RAM, GPU, Disk, Network)."""

    @property
    def name(self) -> str:
        return "resource_monitor"

    @property
    def description(self) -> str:
        return "Monitor system resources: CPU, RAM, GPU (NVIDIA), Disk, Network usage."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["snapshot", "cpu", "memory", "gpu", "disk", "network", "processes", "continuous"],
                    "description": "What to monitor",
                    "default": "snapshot"
                },
                "interval": {"type": "integer", "description": "Interval for continuous monitoring (seconds)", "default": 5},
                "duration": {"type": "integer", "description": "Duration for continuous monitoring (seconds)", "default": 30},
                "top_n": {"type": "integer", "description": "Top N processes to show", "default": 10},
            },
            "required": ["action"],
        }

    async def execute(self, action: str = "snapshot", interval: int = 5, duration: int = 30, top_n: int = 10) -> str:
        if not PSUTIL_AVAILABLE:
            return "❌ psutil not installed. Run: pip install psutil"

        try:
            if action == "snapshot":
                return await self._snapshot()
            elif action == "cpu":
                return await self._cpu_info()
            elif action == "memory":
                return await self._memory_info()
            elif action == "gpu":
                return await self._gpu_info()
            elif action == "disk":
                return await self._disk_info()
            elif action == "network":
                return await self._network_info()
            elif action == "processes":
                return await self._top_processes(top_n)
            elif action == "continuous":
                return await self._continuous_monitor(interval, duration)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"Error: {e}"

    async def _snapshot(self) -> str:
        """Full system snapshot."""
        cpu = await self._cpu_info()
        mem = await self._memory_info()
        gpu = await self._gpu_info()
        disk = await self._disk_info()
        net = await self._network_info()
        return f"{cpu}\n{mem}\n{gpu}\n{disk}\n{net}"

    async def _cpu_info(self) -> str:
        cpu_percent = psutil.cpu_percent(interval=0.5, percpu=True)
        cpu_freq = psutil.cpu_freq()
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)

        out = ["🖥️ **CPU**"]
        out.append(f"  Usage: {sum(cpu_percent)/len(cpu_percent):.1f}% (per core: {', '.join(f'{c:.1f}%' for c in cpu_percent)})")
        out.append(f"  Cores: {psutil.cpu_count(logical=False)} physical, {psutil.cpu_count(logical=True)} logical")
        if cpu_freq:
            out.append(f"  Freq: {cpu_freq.current:.0f} MHz (min: {cpu_freq.min:.0f}, max: {cpu_freq.max:.0f})")
        out.append(f"  Load avg: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}")
        return "\n".join(out)

    async def _memory_info(self) -> str:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        out = ["💾 **RAM**"]
        out.append(f"  Used: {mem.used/1024**3:.2f} / {mem.total/1024**3:.2f} GB ({mem.percent}%)")
        out.append(f"  Available: {mem.available/1024**3:.2f} GB")
        out.append(f"  Swap: {swap.used/1024**3:.2f} / {swap.total/1024**3:.2f} GB ({swap.percent}%)")
        return "\n".join(out)

    async def _gpu_info(self) -> str:
        """Get GPU info via nvidia-smi."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return "🎮 **GPU**: nvidia-smi not available"

            out = ["🎮 **GPU (NVIDIA)**"]
            for i, line in enumerate(result.stdout.strip().split('\n')):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 6:
                    name, mem_used, mem_total, util, temp, power = parts[:6]
                    out.append(f"  GPU {i}: {name}")
                    out.append(f"    VRAM: {mem_used} / {mem_total} MB ({int(mem_used)/int(mem_total)*100:.1f}%)")
                    out.append(f"    Util: {util}% | Temp: {temp}°C | Power: {power} W")
            return "\n".join(out)
        except FileNotFoundError:
            return "🎮 **GPU**: nvidia-smi not found (CPU only?)"
        except Exception as e:
            return f"🎮 **GPU**: Error - {e}"

    async def _disk_info(self) -> str:
        out = ["💿 **Disk**"]
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                out.append(f"  {part.device} ({part.mountpoint}): {usage.used/1024**3:.1f}/{usage.total/1024**3:.1f} GB ({usage.percent}%)")
            except PermissionError:
                out.append(f"  {part.device} ({part.mountpoint}): Access denied")
        return "\n".join(out)

    async def _network_info(self) -> str:
        net = psutil.net_io_counters()
        out = ["🌐 **Network**"]
        out.append(f"  Sent: {net.bytes_sent/1024**2:.2f} MB")
        out.append(f"  Recv: {net.bytes_recv/1024**2:.2f} MB")
        out.append(f"  Packets: {net.packets_sent} sent, {net.packets_recv} recv")
        out.append(f"  Errors: {net.errin} in, {net.errout} out")
        return "\n".join(out)

    async def _top_processes(self, top_n: int) -> str:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info']):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        procs.sort(key=lambda x: x.get('cpu_percent', 0) or 0, reverse=True)
        out = [f"⚙️ **Top {top_n} Processes by CPU**"]
        for i, p in enumerate(procs[:top_n], 1):
            mem_mb = p.get('memory_info').rss / 1024**2 if p.get('memory_info') else 0
            out.append(f"  {i}. {p['name']} (PID: {p['pid']}) - CPU: {p.get('cpu_percent', 0):.1f}% | RAM: {mem_mb:.1f} MB")
        return "\n".join(out)

    async def _continuous_monitor(self, interval: int, duration: int) -> str:
        import time
        end_time = time.time() + duration
        snapshots = []

        while time.time() < end_time:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            snapshots.append((cpu, mem))
            await asyncio.sleep(interval)

        if not snapshots:
            return "No data collected"

        avg_cpu = sum(s[0] for s in snapshots) / len(snapshots)
        avg_mem = sum(s[1] for s in snapshots) / len(snapshots)
        max_cpu = max(s[0] for s in snapshots)
        max_mem = max(s[1] for s in snapshots)

        out = [f"📊 **Continuous Monitor ({len(snapshots)} samples over {duration}s)**"]
        out.append(f"  CPU:  avg={avg_cpu:.1f}%  max={max_cpu:.1f}%")
        out.append(f"  RAM:  avg={avg_mem:.1f}%  max={max_mem:.1f}%")
        return "\n".join(out)


class ModelRouterTool(Tool):
    """
    Automatic model routing with fallback.
    Tries models in order, falls back on rate limits/errors.
    """

    def __init__(self):
        self.current_model_index = 0
        self.use_free = True
        self._client = None
        # Load model lists from config
        from core.config import get_settings
        settings = get_settings()
        self.FREE_MODELS = settings.free_models
        self.PAID_MODELS = settings.paid_models

    @property
    def name(self) -> str:
        return "model_router"

    @property
    def description(self) -> str:
        return "Automatic model routing with fallback. Tries free models first, falls back to paid on rate limits."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["chat", "get_current", "set_model", "list_models", "toggle_free", "reset"],
                    "description": "Action to perform"
                },
                "message": {"type": "string", "description": "Message to send (for chat)"},
                "model": {"type": "string", "description": "Specific model to use (for set_model)"},
                "temperature": {"type": "number", "description": "Temperature", "default": 0.7},
                "max_tokens": {"type": "integer", "description": "Max tokens", "default": 4096},
                "system_prompt": {"type": "string", "description": "System prompt"},
            },
            "required": ["action"],
        }

    def _get_models(self) -> List[str]:
        return self.FREE_MODELS if self.use_free else self.PAID_MODELS

    def _get_client(self):
        if self._client is None:
            from core.openrouter_client import get_client
            self._client = get_client()
        return self._client

    async def execute(self, action: str, message: str = "", model: str = "",
                      temperature: float = 0.7, max_tokens: int = 4096,
                      system_prompt: str = "") -> str:
        if action == "get_current":
            models = self._get_models()
            current = models[self.current_model_index] if models else "none"
            return f"Current model: {current}\nMode: {'Free' if self.use_free else 'Paid'}\nIndex: {self.current_model_index}/{len(models)-1}"

        elif action == "list_models":
            free = "\n  ".join(self.FREE_MODELS)
            paid = "\n  ".join(self.PAID_MODELS)
            return f"**Free models:**\n  {free}\n\n**Paid models:**\n  {paid}"

        elif action == "set_model":
            if not model:
                return "❌ Model required"
            models = self._get_models()
            if model in models:
                self.current_model_index = models.index(model)
                return f"✅ Model set to: {model}"
            return f"❌ Model not in current list. Use 'list_models' to see available."

        elif action == "toggle_free":
            self.use_free = not self.use_free
            self.current_model_index = 0
            return f"🔄 Switched to {'Free' if self.use_free else 'Paid'} models"

        elif action == "reset":
            self.current_model_index = 0
            return "🔄 Model index reset to 0"

        elif action == "chat":
            if not message:
                return "❌ Message required for chat"

            models = self._get_models()
            if not models:
                return "❌ No models available"

            client = self._get_client()

            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": message})

            last_error = None
            for attempt in range(len(models)):
                current_model = models[self.current_model_index]
                try:
                    response = await client.chat_completion(
                        messages=messages,
                        model=current_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    if hasattr(response, 'choices') and response.choices:
                        content = response.choices[0].message.content
                        return f"✅ **{current_model}**\n\n{content}"

                except Exception as e:
                    last_error = str(e)
                    # Check if rate limit
                    if "429" in last_error or "rate limit" in last_error.lower():
                        # Move to next model
                        self.current_model_index = (self.current_model_index + 1) % len(models)
                        continue
                    # Other error - try next model too
                    self.current_model_index = (self.current_model_index + 1) % len(models)
                    continue

            return f"❌ All models failed. Last error: {last_error}"

        else:
            return f"❌ Unknown action: {action}"


class WebSearchTool(Tool):
    """Search the web using DuckDuckGo HTML scraping (no API key required)."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for information using DuckDuckGo."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Maximum results", "default": 5},
            },
            "required": ["query"],
        }

    async def execute(self, query: str, max_results: int = 5) -> str:
        try:
            import urllib.parse
            import urllib.request
            import re

            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8", errors="replace")

            # Parse results from HTML
            results = []
            # Match result snippets
            pattern = r'class="result__snippet">(.*?)</a>'
            matches = re.findall(pattern, html, re.DOTALL)

            for i, match in enumerate(matches[:max_results]):
                clean = re.sub(r"<[^>]+>", "", match)
                clean = re.sub(r"\s+", " ", clean).strip()
                if clean:
                    results.append(f"{i+1}. {clean}")

            # Also try to get titles and URLs
            title_pattern = r'class="result__title">.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
            title_matches = re.findall(title_pattern, html, re.DOTALL)

            if title_matches and results:
                formatted = []
                for i, (url, title) in enumerate(title_matches[:max_results]):
                    clean_title = re.sub(r"<[^>]+>", "", title).strip()
                    if i < len(results):
                        formatted.append(f"{i+1}. {clean_title}\n   {results[i]}\n   URL: {url}")
                    else:
                        formatted.append(f"{i+1}. {clean_title}\n   URL: {url}")
                return "\n\n".join(formatted) if formatted else "No results found"

            return "\n\n".join(results) if results else "No results found"

        except Exception as e:
            return f"Error searching web: {e}"


class HTTPRequestTool(Tool):
    """Make HTTP requests to APIs or websites."""

    @property
    def name(self) -> str:
        return "http_request"

    @property
    def description(self) -> str:
        return "Make an HTTP request (GET, POST, PUT, DELETE, etc.) to a URL."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to request"},
                "method": {"type": "string", "description": "HTTP method", "default": "GET", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]},
                "headers": {"type": "object", "description": "Request headers", "default": {}},
                "body": {"type": "string", "description": "Request body (for POST/PUT/PATCH)"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["url"],
        }

    async def execute(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, body: Optional[str] = None, timeout: int = 30) -> str:
        try:
            import urllib.request
            import urllib.error
            import json

            headers = headers or {}
            data = body.encode("utf-8") if body else None

            req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)

            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode("utf-8", errors="replace")
                status = response.status

            # Try to parse JSON for pretty output
            try:
                parsed = json.loads(content)
                content = json.dumps(parsed, indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                pass

            return f"Status: {status}\n\n{content}"

        except urllib.error.HTTPError as e:
            return f"HTTP Error {e.code}: {e.read().decode('utf-8', errors='replace')}"
        except urllib.error.URLError as e:
            return f"URL Error: {e}"
        except Exception as e:
            return f"Error making request: {e}"


class JSONTool(Tool):
    """Parse, query, and manipulate JSON data."""

    @property
    def name(self) -> str:
        return "json_tool"

    @property
    def description(self) -> str:
        return "Parse, query, or manipulate JSON data."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action to perform", "enum": ["parse", "get", "set", "keys", "pretty"]},
                "json_string": {"type": "string", "description": "JSON string to operate on"},
                "path": {"type": "string", "description": "JSONPath-like path (e.g., 'data.items[0].name')", "default": ""},
                "value": {"type": "string", "description": "Value to set (for 'set' action)"},
            },
            "required": ["action", "json_string"],
        }

    async def execute(self, action: str, json_string: str, path: str = "", value: Optional[str] = None) -> str:
        try:
            import json

            data = json.loads(json_string)

            if action == "parse":
                return json.dumps(data, indent=2, ensure_ascii=False)

            elif action == "pretty":
                return json.dumps(data, indent=2, ensure_ascii=False)

            elif action == "keys":
                if isinstance(data, dict):
                    return "\n".join(f"  {k}: {type(v).__name__}" for k, v in data.items())
                elif isinstance(data, list):
                    return f"List with {len(data)} items: {[type(item).__name__ for item in data[:5]]}"
                else:
                    return f"Type: {type(data).__name__}"

            elif action == "get":
                if not path:
                    return json.dumps(data, indent=2, ensure_ascii=False)

                # Simple path traversal (supports dict keys and list indices)
                current = data
                parts = path.split(".")
                for part in parts:
                    if part == "":
                        continue
                    # Handle array indices like "items[0]"
                    match = re.match(r"^(.+)\[(\d+)\]$", part)
                    if match:
                        key, idx = match.groups()
                        if key:
                            current = current.get(key) if isinstance(current, dict) else current
                        current = current[int(idx)] if isinstance(current, list) and int(idx) < len(current) else None
                    else:
                        current = current.get(part) if isinstance(current, dict) else None
                    if current is None:
                        return f"Path not found: {path}"

                return json.dumps(current, indent=2, ensure_ascii=False) if isinstance(current, (dict, list)) else str(current)

            elif action == "set":
                if not path or value is None:
                    return "Error: 'path' and 'value' required for 'set' action"
                try:
                    set_value = json.loads(value)
                except json.JSONDecodeError:
                    set_value = value

                # Navigate and set
                parts = path.split(".")
                current = data
                for i, part in enumerate(parts[:-1]):
                    if part == "":
                        continue
                    match = re.match(r"^(.+)\[(\d+)\]$", part)
                    if match:
                        key, idx = match.groups()
                        if key:
                            current = current.setdefault(key, {})
                        current = current[int(idx)]
                    else:
                        current = current.setdefault(part, {})
                last_part = parts[-1]
                match = re.match(r"^(.+)\[(\d+)\]$", last_part)
                if match:
                    key, idx = match.groups()
                    if key:
                        current = current.setdefault(key, [])
                    current[int(idx)] = set_value
                else:
                    current[last_part] = set_value

                return json.dumps(data, indent=2, ensure_ascii=False)

            else:
                return f"Unknown action: {action}"

        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        except Exception as e:
            return f"Error: {e}"


class FileSearchTool(Tool):
    """Search for text patterns in files (grep-like)."""

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return "Search for text patterns in files within a directory."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory path to search", "default": "."},
                "file_pattern": {"type": "string", "description": "File glob pattern", "default": "**/*"},
                "max_results": {"type": "integer", "description": "Maximum results", "default": 50},
                "case_sensitive": {"type": "boolean", "description": "Case sensitive search", "default": False},
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str = ".", file_pattern: str = "**/*", max_results: int = 50, case_sensitive: bool = False) -> str:
        try:
            import re
            from pathlib import Path

            dir_path = Path(path).resolve()
            if not dir_path.exists() or not dir_path.is_dir():
                return f"Error: Directory not found: {path}"

            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)

            results = []
            for file_path in dir_path.rglob(file_pattern):
                if not file_path.is_file():
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()
                    for i, line in enumerate(lines, 1):
                        if regex.search(line):
                            rel_path = file_path.relative_to(dir_path)
                            results.append(f"{rel_path}:{i}: {line.strip()}")
                            if len(results) >= max_results:
                                break
                    if len(results) >= max_results:
                        break
                except Exception:
                    continue

            return "\n".join(results) if results else "No matches found"

        except re.error as e:
            return f"Invalid regex pattern: {e}"
        except Exception as e:
            return f"Error searching files: {e}"


class WebScrapeTool(Tool):
    """Scrape and parse web pages (HTML parsing via BeautifulSoup if available, fallback to regex)."""

    @property
    def name(self) -> str:
        return "web_scrape"

    @property
    def description(self) -> str:
        return "Fetch and parse a web page, extract text, links, or specific elements."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to scrape"},
                "selector": {"type": "string", "description": "CSS selector to extract (optional)"},
                "extract": {"type": "string", "description": "What to extract: 'text', 'html', 'links', 'title', 'all'", "default": "text"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["url"],
        }

    async def execute(self, url: str, selector: str = "", extract: str = "text", timeout: int = 30) -> str:
        try:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; EverlayBot/1.0)"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                html = response.read().decode("utf-8", errors="replace")

            # Try BeautifulSoup if available
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")

                if selector:
                    elements = soup.select(selector)
                    if not elements:
                        return f"No elements found for selector: {selector}"
                    if extract == "text":
                        return "\n\n".join(el.get_text(strip=True) for el in elements)
                    elif extract == "html":
                        return "\n\n".join(str(el) for el in elements)
                    elif extract == "links":
                        links = []
                        for el in elements:
                            for a in el.find_all("a", href=True):
                                links.append(f"{a.get_text(strip=True)}: {a['href']}")
                        return "\n".join(links) if links else "No links found"
                    elif extract == "all":
                        return str(elements[0])
                else:
                    # No selector - extract from whole page
                    if extract == "text":
                        # Remove scripts and styles
                        for tag in soup(["script", "style", "noscript"]):
                            tag.decompose()
                        return soup.get_text(separator="\n", strip=True)[:10000]
                    elif extract == "title":
                        return soup.title.string.strip() if soup.title else "No title"
                    elif extract == "links":
                        links = [f"{a.get_text(strip=True)}: {a['href']}" for a in soup.find_all("a", href=True)]
                        return "\n".join(links[:100])
                    elif extract == "html":
                        return str(soup)[:20000]
                    elif extract == "all":
                        return str(soup)[:20000]

            except ImportError:
                # Fallback: regex-based extraction
                if extract == "text":
                    # Strip tags
                    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<[^>]+>", "\n", text)
                    text = re.sub(r"\n\s*\n", "\n\n", text)
                    return text.strip()[:10000]
                elif extract == "title":
                    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                    return match.group(1).strip() if match else "No title"
                elif extract == "links":
                    links = re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
                    return "\n".join(f"{text.strip()}: {url}" for url, text in links[:100])
                elif extract == "html":
                    return html[:20000]

            return "Unknown extract type"

        except urllib.error.HTTPError as e:
            return f"HTTP Error {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}"
        except urllib.error.URLError as e:
            return f"URL Error: {e}"
        except Exception as e:
            return f"Error scraping: {e}"


class GitTool(Tool):
    """Git repository operations."""

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Execute git commands: status, diff, log, commit, branch, etc."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Git subcommand", "enum": ["status", "diff", "log", "branch", "show", "add", "commit", "push", "pull", "checkout", "remote", "stash"]},
                "args": {"type": "string", "description": "Additional arguments", "default": ""},
                "repo_path": {"type": "string", "description": "Repository path", "default": "."},
            },
            "required": ["command"],
        }

    async def execute(self, command: str, args: str = "", repo_path: str = ".") -> str:
        try:
            repo = Path(repo_path).resolve()
            if not (repo / ".git").exists():
                return f"Error: Not a git repository: {repo_path}"

            full_cmd = f"git {command} {args}".strip()

            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                cwd=repo,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            result = []
            if stdout:
                result.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                result.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")
            if proc.returncode != 0:
                result.append(f"Exit code: {proc.returncode}")

            output = "\n".join(result)
            return output if output else "Command executed (no output)"

        except Exception as e:
            return f"Error executing git: {e}"


class DatabaseTool(Tool):
    """SQLite database operations."""

    @property
    def name(self) -> str:
        return "database"

    @property
    def description(self) -> str:
        return "Execute SQL queries on SQLite databases: select, insert, update, create, schema."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action to perform", "enum": ["query", "execute", "schema", "tables", "create"]},
                "database": {"type": "string", "description": "Database file path", "default": "everlay.db"},
                "sql": {"type": "string", "description": "SQL statement"},
                "params": {"type": "array", "description": "Query parameters", "items": {"type": "string"}},
            },
            "required": ["action", "database"],
        }

    async def execute(self, action: str, database: str, sql: str = "", params: Optional[List[str]] = None) -> str:
        try:
            import sqlite3

            db_path = Path(database).resolve()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            params = params or []

            if action == "query":
                if not sql:
                    return "Error: SQL required for query"
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                if not rows:
                    return "No results"
                cols = rows[0].keys()
                out = [" | ".join(cols)]
                out.append("-" * len(out[0]))
                for row in rows:
                    out.append(" | ".join(str(row[c]) for c in cols))
                return "\n".join(out)

            elif action == "execute":
                if not sql:
                    return "Error: SQL required for execute"
                cursor.execute(sql, params)
                conn.commit()
                return f"Rows affected: {cursor.rowcount}"

            elif action == "schema":
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
                return "\n\n".join(row[0] for row in cursor.fetchall()) or "No tables"

            elif action == "tables":
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                return "\n".join(row[0] for row in cursor.fetchall()) or "No tables"

            elif action == "create":
                if not sql:
                    return "Error: SQL required for create"
                cursor.execute(sql)
                conn.commit()
                return "Table created"

            else:
                return f"Unknown action: {action}"

        except sqlite3.Error as e:
            return f"SQLite error: {e}"
        except Exception as e:
            return f"Error: {e}"
        finally:
            try:
                conn.close()
            except:
                pass


class CSVTool(Tool):
    """CSV/Excel file operations."""

    @property
    def name(self) -> str:
        return "csv_tool"

    @property
    def description(self) -> str:
        return "Read, write, filter, and transform CSV files."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action to perform", "enum": ["read", "write", "filter", "columns", "stats", "convert"]},
                "path": {"type": "string", "description": "CSV file path"},
                "output": {"type": "string", "description": "Output file path (for write/convert)"},
                "query": {"type": "string", "description": "Filter query (e.g., 'age > 25')"},
                "columns": {"type": "array", "description": "Columns to select", "items": {"type": "string"}},
                "delimiter": {"type": "string", "description": "CSV delimiter", "default": ","},
                "data": {"type": "string", "description": "JSON string of rows to write"},
            },
            "required": ["action", "path"],
        }

    async def execute(self, action: str, path: str, output: str = "", query: str = "", columns: Optional[List[str]] = None, delimiter: str = ",", data: str = "") -> str:
        try:
            import json
            import csv as csv_module

            file_path = Path(path).resolve()

            if action == "read":
                if not file_path.exists():
                    return f"Error: File not found: {path}"
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv_module.DictReader(f, delimiter=delimiter)
                    rows = list(reader)
                if not rows:
                    return "Empty file"
                if columns:
                    rows = [{c: r[c] for c in columns if c in r} for r in rows]
                out = [delimiter.join(rows[0].keys())]
                for r in rows[:100]:
                    out.append(delimiter.join(str(r.get(c, "")) for c in rows[0].keys()))
                if len(rows) > 100:
                    out.append(f"... ({len(rows)} total rows)")
                return "\n".join(out)

            elif action == "write":
                if not data:
                    return "Error: data required for write"
                rows = json.loads(data)
                if not rows:
                    return "Error: empty data"
                fieldnames = list(rows[0].keys())
                out_path = Path(output).resolve() if output else file_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv_module.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
                    writer.writeheader()
                    writer.writerows(rows)
                return f"Written {len(rows)} rows to {out_path}"

            elif action == "filter":
                if not query:
                    return "Error: query required for filter"
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv_module.DictReader(f, delimiter=delimiter)
                    rows = list(reader)
                # Safe expression evaluation using ast
                import ast
                import operator

                # Supported operators
                operators = {
                    ast.Add: operator.add,
                    ast.Sub: operator.sub,
                    ast.Mult: operator.mul,
                    ast.Div: operator.truediv,
                    ast.FloorDiv: operator.floordiv,
                    ast.Mod: operator.mod,
                    ast.Pow: operator.pow,
                    ast.Eq: operator.eq,
                    ast.NotEq: operator.ne,
                    ast.Lt: operator.lt,
                    ast.LtE: operator.le,
                    ast.Gt: operator.gt,
                    ast.GtE: operator.ge,
                    ast.And: lambda x, y: x and y,
                    ast.Or: lambda x, y: x or y,
                    ast.Not: operator.not_,
                    ast.UAdd: operator.pos,
                    ast.USub: operator.neg,
                }

                def eval_node(node, context):
                    """Safely evaluate an AST node."""
                    if isinstance(node, ast.Constant):  # Python 3.8+
                        return node.value
                    elif isinstance(node, ast.Name):
                        if node.id in context:
                            return context[node.id]
                        raise ValueError(f"Unknown variable: {node.id}")
                    elif isinstance(node, ast.BinOp):
                        left = eval_node(node.left, context)
                        right = eval_node(node.right, context)
                        op_type = type(node.op)
                        if op_type in operators:
                            return operators[op_type](left, right)
                        raise ValueError(f"Unsupported operator: {op_type}")
                    elif isinstance(node, ast.Compare):
                        left = eval_node(node.left, context)
                        for op, comparator in zip(node.ops, node.comparators):
                            right = eval_node(comparator, context)
                            op_type = type(op)
                            if op_type in operators:
                                if not operators[op_type](left, right):
                                    return False
                                left = right
                            else:
                                raise ValueError(f"Unsupported comparison: {op_type}")
                        return True
                    elif isinstance(node, ast.BoolOp):
                        values = [eval_node(v, context) for v in node.values]
                        op_type = type(node.op)
                        if op_type == ast.And:
                            return all(values)
                        elif op_type == ast.Or:
                            return any(values)
                        raise ValueError(f"Unsupported bool operator: {op_type}")
                    elif isinstance(node, ast.UnaryOp):
                        operand = eval_node(node.operand, context)
                        op_type = type(node.op)
                        if op_type in operators:
                            return operators[op_type](operand)
                        raise ValueError(f"Unsupported unary operator: {op_type}")
                    else:
                        raise ValueError(f"Unsupported expression type: {type(node).__name__}")

                def safe_eval(expr, context):
                    """Safely evaluate a simple expression."""
                    try:
                        tree = ast.parse(expr, mode='eval')
                        return eval_node(tree.body, context)
                    except Exception as e:
                        raise ValueError(f"Invalid expression: {e}")

                # Parse query once
                try:
                    # Test parse
                    ast.parse(query, mode='eval')
                except SyntaxError as e:
                    return f"Invalid query syntax: {e}"

                filtered = []
                for row in rows:
                    # Convert values for comparison
                    test_row = {}
                    for k, v in row.items():
                        try:
                            test_row[k] = float(v) if "." in v else int(v)
                        except:
                            test_row[k] = v
                    try:
                        if safe_eval(query, test_row):
                            filtered.append(row)
                    except Exception as e:
                        return f"Error evaluating query: {e}"

                return f"Matched {len(filtered)} rows:\n" + "\n".join(delimiter.join(str(r.get(c, "")) for c in rows[0].keys()) for r in filtered[:50])

            elif action == "columns":
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv_module.reader(f, delimiter=delimiter)
                    header = next(reader, [])
                return "Columns:\n" + "\n".join(f"  {c}" for c in header)

            elif action == "stats":
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv_module.DictReader(f, delimiter=delimiter)
                    rows = list(reader)
                if not rows:
                    return "Empty file"
                stats = []
                for col in rows[0].keys():
                    vals = [r[col] for r in rows if r[col]]
                    try:
                        nums = [float(v) for v in vals]
                        stats.append(f"{col}: count={len(nums)}, min={min(nums)}, max={max(nums)}, avg={sum(nums)/len(nums):.2f}")
                    except:
                        unique = len(set(vals))
                        stats.append(f"{col}: count={len(vals)}, unique={unique}, sample={vals[:3]}")
                return "\n".join(stats)

            elif action == "convert":
                if not output:
                    return "Error: output path required for convert"
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv_module.DictReader(f, delimiter=delimiter)
                    rows = list(reader)
                out_path = Path(output).resolve()
                if out_path.suffix == ".json":
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(rows, f, indent=2, ensure_ascii=False)
                    return f"Converted to JSON: {out_path}"
                else:
                    return "Only CSV->JSON conversion supported"

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            return f"Error: {e}"


class RAGTool(Tool):
    """Инструмент для работы с RAG системой (база знаний)."""

    def __init__(self):
        # Ленивая инициализация чтобы избежать циклических импортов
        self._db = None
        self._embedder = None

    @property
    def name(self) -> str:
        return "rag"

    @property
    def description(self) -> str:
        return "Работа с базой знаний: добавление документов, семантический поиск, теги."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "search", "get", "list", "delete", "tags"],
                    "description": "Действие"
                },
                "title": {"type": "string", "description": "Заголовок документа (для add)"},
                "content": {"type": "string", "description": "Содержимое документа (для add)"},
                "source": {"type": "string", "description": "Источник (файл, URL, заметка)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Теги"},
                "query": {"type": "string", "description": "Поисковый запрос (для search)"},
                "top_k": {"type": "integer", "description": "Количество результатов", "default": 5},
                "doc_id": {"type": "string", "description": "ID документа (для get/delete)"},
                "tag_name": {"type": "string", "description": "Имя тега (для tags)"},
                "tag_color": {"type": "string", "description": "Цвет тега (hex)", "default": "#4ec9b0"}
            },
            "required": ["action"]
        }

    def _get_db(self):
        if self._db is None:
            from core.rag import RAGDatabase
            self._db = RAGDatabase()
        return self._db

    def _get_embedder(self):
        if self._embedder is None:
            from core.rag import EmbeddingProvider
            self._embedder = EmbeddingProvider()
        return self._embedder

    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action")

        try:
            if action == "add":
                title = kwargs.get("title", "Без названия")
                content = kwargs.get("content", "")
                source = kwargs.get("source", "")
                tags = kwargs.get("tags", [])

                # Получаем эмбеддинг
                embedding = await self._get_embedder().get_embedding(content)

                doc_id = self._get_db().add_document(
                    title=title,
                    content=content,
                    source=source,
                    tags=tags,
                    embedding=embedding
                )
                return f"✅ Документ добавлен (ID: {doc_id[:8]}...)\nТеги: {', '.join(tags) if tags else 'нет'}"

            elif action == "search":
                query = kwargs.get("query", "")
                top_k = kwargs.get("top_k", 5)
                if not query:
                    return "❌ Пустой запрос"

                embedding = await self._get_embedder().get_embedding(query)
                results = self._get_db().search_similar(embedding, top_k=top_k)

                if not results:
                    return "🔍 Ничего не найдено"

                out = [f"🔍 Найдено {len(results)} результатов:\n"]
                for i, r in enumerate(results, 1):
                    tags_str = f" [{', '.join(r['tags'])}]" if r['tags'] else ""
                    out.append(f"{i}. **{r['title']}** (score: {r['score']:.3f}){tags_str}")
                    out.append(f"   {r['content'][:200]}...")
                    out.append(f"   Источник: {r['source'] or 'не указан'}")
                    out.append("")
                return "\n".join(out)

            elif action == "get":
                doc_id = kwargs.get("doc_id", "")
                doc = self._get_db().get_document(doc_id)
                if not doc:
                    return f"❌ Документ не найден: {doc_id}"
                tags_str = f"\nТеги: {', '.join(doc['tags'])}" if doc['tags'] else ""
                return f"📄 **{doc['title']}**\nID: {doc['id']}\nИсточник: {doc['source'] or 'не указан'}{tags_str}\n\n{doc['content']}"

            elif action == "list":
                docs = self._get_db().list_documents(limit=20)
                if not docs:
                    return "📭 База пуста"
                out = ["📚 Документы в базе:\n"]
                for d in docs:
                    import json
                    try:
                        tags = json.loads(d['tags']) if d['tags'] else []
                    except:
                        tags = []
                    tags_str = f" [{', '.join(tags)}]" if tags else ""
                    out.append(f"• {d['title']} (ID: {d['id'][:8]}...){tags_str} — {d['source'] or 'нет источника'}")
                return "\n".join(out)

            elif action == "delete":
                doc_id = kwargs.get("doc_id", "")
                if self._get_db().delete_document(doc_id):
                    return f"🗑️ Документ удалён: {doc_id}"
                return f"❌ Не найден: {doc_id}"

            elif action == "tags":
                tag_name = kwargs.get("tag_name", "")
                tag_color = kwargs.get("tag_color", "#4ec9b0")
                if tag_name:
                    self._get_db().add_tag(tag_name, tag_color)
                    return f"🏷️ Тег добавлен: {tag_name}"
                tags = self._get_db().get_tags()
                if not tags:
                    return "🏷️ Тегов нет"
                return "🏷️ Теги:\n" + "\n".join(f"• {t['name']} ({t['color']})" for t in tags)

            else:
                return f"❌ Неизвестное действие: {action}"

        except Exception as e:
            from core.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"RAG error: {e}")
            return f"❌ Ошибка RAG: {e}"


# Tool registry
BUILTIN_TOOLS: Dict[str, Tool] = {
    "read_file": FileReadTool(),
    "write_file": FileWriteTool(),
    "list_files": FileListTool(),
    "shell": ShellTool(),
    "python": PythonTool(),
    "code_interpreter": CodeInterpreterTool(),
    "web_search": WebSearchTool(),
    "http_request": HTTPRequestTool(),
    "json_tool": JSONTool(),
    "search_files": FileSearchTool(),
    "web_scrape": WebScrapeTool(),
    "git": GitTool(),
    "database": DatabaseTool(),
    "csv_tool": CSVTool(),
    "rag": RAGTool(),
    "resource_monitor": ResourceMonitorTool(),
    "model_router": ModelRouterTool(),
}


def get_builtin_tools(names: Optional[List[str]] = None) -> List[Tool]:
    """Get builtin tools by name."""
    if names is None:
        return list(BUILTIN_TOOLS.values())
    return [BUILTIN_TOOLS[name] for name in names if name in BUILTIN_TOOLS]