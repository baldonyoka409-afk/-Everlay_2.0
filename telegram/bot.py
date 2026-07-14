"""
Telegram bot for Everlay.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
    BotCommandScopeDefault,
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from core.config import get_settings
from core.logging_config import get_logger
from core.exceptions import TelegramError, ConfigurationError
from agents.base import AgentContext, AgentStatus, BaseAgent
from agents.presets import AgentFactory, DefaultAgent, CodeAgent, ChatAgent

logger = get_logger(__name__)


@dataclass
class UserSession:
    """User session data."""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    current_agent: str = "default"
    agent_instance: Optional[BaseAgent] = None
    context: Optional[AgentContext] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    message_count: int = 0


class TelegramBot:
    """
    Telegram bot for interacting with AI agents.
    """

    def __init__(self):
        self.settings = get_settings()
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.router = Router()
        self.sessions: Dict[int, UserSession] = {}
        self._running = False

        # Register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register message handlers."""
        self.router.message(CommandStart())(self.cmd_start)
        self.router.message(Command("help"))(self.cmd_help)
        self.router.message(Command("agent"))(self.cmd_agent)
        self.router.message(Command("agents"))(self.cmd_agents)
        self.router.message(Command("clear"))(self.cmd_clear)
        self.router.message(Command("status"))(self.cmd_status)
        self.router.message(Command("model"))(self.cmd_model)
        self.router.message(Command("build"))(self.cmd_build)
        self.router.message(Command("apk"))(self.cmd_apk)
        self.router.message(Command("apkwindows"))(self.cmd_apkwindows)
        self.router.message(Command("build_status"))(self.cmd_build_status)
        self.router.callback_query(F.data.startswith("agent_"))(self.callback_agent)
        self.router.callback_query(F.data == "download_apk")(self.callback_download_apk)
        self.router.callback_query(F.data == "download_exe")(self.callback_download_exe)
        self.router.callback_query(F.data == "build_apk")(self.callback_build_apk)
        self.router.callback_query(F.data == "build_exe")(self.callback_build_exe)
        self.router.message(F.text)(self.handle_message)

    async def start(self) -> None:
        """Start the bot."""
        if not self.settings.telegram_bot_token:
            raise ConfigurationError("Telegram bot token not configured")

        self.bot = Bot(
            token=self.settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )
        self.dp = Dispatcher()
        self.dp.include_router(self.router)

        # Set bot commands
        await self.bot.set_my_commands([
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="help", description="Show help"),
            BotCommand(command="agent", description="Switch agent"),
            BotCommand(command="agents", description="List available agents"),
            BotCommand(command="clear", description="Clear conversation history"),
            BotCommand(command="status", description="Show current status"),
            BotCommand(command="model", description="Change model"),
            BotCommand(command="build", description="Check Android build status"),
            BotCommand(command="apk", description="Send Android APK"),
            BotCommand(command="apkwindows", description="Send Windows EXE"),
        ], scope=BotCommandScopeDefault())

        self._running = True
        logger.info("Telegram bot started")

        # Start polling
        await self.dp.start_polling(self.bot)

    async def stop(self) -> None:
        """Stop the bot."""
        self._running = False
        if self.bot:
            await self.bot.session.close()
        logger.info("Telegram bot stopped")

    def _get_session(self, user_id: int, username: str = None, first_name: str = None) -> UserSession:
        """Get or create user session."""
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(
                user_id=user_id,
                username=username,
                first_name=first_name,
            )
        session = self.sessions[user_id]
        session.username = username or session.username
        session.first_name = first_name or session.first_name
        session.updated_at = datetime.utcnow()
        return session

    def _get_agent(self, session: UserSession) -> BaseAgent:
        """Get or create agent for session."""
        if session.agent_instance is None or session.agent_instance.name != session.current_agent:
            session.agent_instance = AgentFactory.create(session.current_agent)
            if session.context is None:
                session.context = AgentContext(
                    agent_id=session.agent_instance.name,
                    conversation_id=str(user_id),
                    user_id=session.user_id,
                )
        return session.agent_instance

    def _is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed."""
        allowed = self.settings.telegram_allowed_users
        if not allowed:
            return True  # Allow all if not configured
        return user_id in allowed

    async def cmd_start(self, message: Message) -> None:
        """Handle /start command."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        session = self._get_session(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )

        welcome = (
            f"👋 Welcome, {session.first_name or 'there'}!\n\n"
            f"Everlay AI Environment - Your personal AI workspace.\n\n"
            f"Current agent: **{session.current_agent}**\n"
            f"Available agents: {', '.join(AgentFactory.list_types())}\n\n"
            f"Use /help to see available commands."
        )
        await message.answer(welcome)

    async def cmd_help(self, message: Message) -> None:
        """Handle /help command."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        help_text = (
            "📚 **Available Commands**\n\n"
            "/start - Start the bot\n"
            "/help - Show this help\n"
            "/agent <name> - Switch agent (default, code, chat)\n"
            "/agents - List available agents\n"
            "/clear - Clear conversation history\n"
            "/status - Show current session status\n"
            "/model <name> - Change model (e.g., openai/gpt-4o)\n\n"
            "**Build & Deploy:**\n"
            "/build — Build info & features\n"
            "/apk — Send Android APK\n"
            "/apkwindows — Send Windows EXE\n"
            "/build_status — Check GitHub Actions build\n\n"
            "**Agents:**\n"
            "• **default** - General purpose with tools\n"
            "• **code** - Code-focused, lower temperature\n"
            "• **chat** - Pure conversation, no tools\n\n"
            "Just send a message to chat with the current agent!"
        )
        await message.answer(help_text)

    async def cmd_agents(self, message: Message) -> None:
        """Handle /agents command."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        agents = AgentFactory.list_types()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅ ' if a == 'default' else ''}{a}", callback_data=f"agent_{a}")]
            for a in agents
        ])

        await message.answer(
            "🤖 **Available Agents:**\n\nSelect one to switch:",
            reply_markup=keyboard,
        )

    async def cmd_agent(self, message: Message) -> None:
        """Handle /agent command."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await self.cmd_agents(message)
            return

        agent_name = args[1].strip().lower()
        if agent_name not in AgentFactory.list_types():
            await message.answer(f"❌ Unknown agent: {agent_name}\nAvailable: {', '.join(AgentFactory.list_types())}")
            return

        session = self._get_session(message.from_user.id)
        old_agent = session.current_agent
        session.current_agent = agent_name
        session.agent_instance = None  # Force recreation on next use

        await message.answer(f"🔄 Switched from **{old_agent}** to **{agent_name}**")

    async def callback_agent(self, callback: CallbackQuery) -> None:
        """Handle agent selection callback."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return

        agent_name = callback.data.replace("agent_", "")
        session = self._get_session(callback.from_user.id)
        old_agent = session.current_agent
        session.current_agent = agent_name
        session.agent_instance = None

        await callback.message.edit_text(
            f"🔄 Switched from **{old_agent}** to **{agent_name}**"
        )
        await callback.answer()

    async def callback_download_apk(self, callback: CallbackQuery) -> None:
        """Handle APK download button."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return
        await callback.answer("📥 Preparing APK...")
        # Trigger the APK command
        from aiogram.types import Message
        # Create a fake message to reuse cmd_apk logic
        class FakeMessage:
            def __init__(self, callback):
                self.from_user = callback.from_user
                self.chat = callback.message.chat
                self.bot = callback.bot
                self.message_id = callback.message.message_id
            async def answer(self, text, **kwargs):
                return await callback.message.answer(text, **kwargs)
            async def answer_document(self, document, **kwargs):
                return await callback.message.answer_document(document, **kwargs)
        fake_msg = FakeMessage(callback)
        await self.cmd_apk(fake_msg)

    async def callback_download_exe(self, callback: CallbackQuery) -> None:
        """Handle EXE download button."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return
        await callback.answer("📥 Preparing EXE...")
        from aiogram.types import Message
        class FakeMessage:
            def __init__(self, callback):
                self.from_user = callback.from_user
                self.chat = callback.message.chat
                self.bot = callback.bot
                self.message_id = callback.message.message_id
            async def answer(self, text, **kwargs):
                return await callback.message.answer(text, **kwargs)
            async def answer_document(self, document, **kwargs):
                return await callback.message.answer_document(document, **kwargs)
        fake_msg = FakeMessage(callback)
        await self.cmd_apkwindows(fake_msg)

    async def callback_build_apk(self, callback: CallbackQuery) -> None:
        """Handle build APK button."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return
        await callback.answer("🔨 Opening build instructions...")
        await callback.message.answer(
            "🔨 **Build APK (Linux/WSL only)**\n\n"
            "**Quick start in WSL2:**\n"
            "```bash\n"
            "wsl --install\n"
            "# Restart, then in Ubuntu:\n"
            "sudo apt update && sudo apt install -y \\\n"
            "  git zip unzip openjdk-17-jdk python3-pip \\\n"
            "  autoconf libtool pkg-config zlib1g-dev \\\n"
            "  libncurses5-dev libncursesw5-dev libtinfo5 \\\n"
            "  cmake libffi-dev libssl-dev automake\n"
            "pip install buildozer cython\n"
            "cd ~/everlay\n"
            "export OPENROUTER_API_KEY=\"your-key\"\n"
            "buildozer -v android debug\n"
            "```\n\n"
            "**APK will be in:** `bin/everlay-2.0.0-arm64-v8a-debug.apk`"
        )

    async def callback_build_exe(self, callback: CallbackQuery) -> None:
        """Handle build EXE button."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return
        await callback.answer("🔨 Opening build instructions...")
        await callback.message.answer(
            "🔨 **Build Windows EXE**\n\n"
            "**On Windows:**\n"
            "```cmd\n"
            "pip install pyinstaller\n"
            "python build_exe.py\n"
            "```\n\n"
            "**Output:** `dist/Everlay/Everlay.exe`\n\n"
            "**Requirements:**\n"
            "- Python 3.10+\n"
            "- PyInstaller\n"
            "- All dependencies from requirements.txt"
        )

    async def cmd_clear(self, message: Message) -> None:
        """Handle /clear command."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        session = self._get_session(message.from_user.id)
        if session.agent_instance:
            session.agent_instance.clear_history()
        session.context = None

        await message.answer("🧹 Conversation history cleared")

    async def cmd_status(self, message: Message) -> None:
        """Handle /status command."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        session = self._get_session(message.from_user.id)
        agent = self._get_agent(session)

        status_text = (
            f"📊 **Session Status**\n\n"
            f"User: {session.first_name} (@{session.username or 'none'})\n"
            f"Agent: **{session.current_agent}**\n"
            f"Model: {agent.model}\n"
            f"Temperature: {agent.temperature}\n"
            f"Max tokens: {agent.max_tokens}\n"
            f"Tools: {', '.join(agent.tools.keys()) if agent.tools else 'none'}\n"
            f"Messages: {session.message_count}\n"
            f"Status: {agent.status.value}"
        )
        await message.answer(status_text)

    async def cmd_model(self, message: Message) -> None:
        """Handle /model command."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("Usage: /model <model_name>\nExample: /model openai/gpt-4o")
            return

        model_name = args[1].strip()
        session = self._get_session(message.from_user.id)
        agent = self._get_agent(session)
        old_model = agent.model
        agent.model = model_name

        await message.answer(f"🔄 Model changed from **{old_model}** to **{model_name}**")

    async def cmd_build(self, message: Message) -> None:
        """Handle /build command - show build info with inline buttons."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        build_info = (
            "🤖 **Everlay Build Info**\n\n"
            "**App:** Everlay AI\n"
            "**Package:** org.everlay.everlay\n"
            "**Version:** 2.0.0\n"
            "**Min Android:** 7.0 (API 24)\n"
            "**Target Android:** 14 (API 34)\n"
            "**Architectures:** arm64-v8a, armeabi-v7a\n\n"
            "**Features:**\n"
            "• FastAPI server on localhost:8000\n"
            "• WebView UI (WebKit)\n"
            "• Foreground service for background\n"
            "• All agents & tools included\n"
            "• RAG with local embeddings\n\n"
            "**Available Downloads:**"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Download Android APK", callback_data="download_apk")],
            [InlineKeyboardButton(text="💻 Download Windows EXE", callback_data="download_exe")],
            [InlineKeyboardButton(text="🔨 Build APK (Linux/WSL)", callback_data="build_apk")],
            [InlineKeyboardButton(text="🔨 Build EXE (Windows)", callback_data="build_exe")],
            [InlineKeyboardButton(text="📊 Build Status", callback_data="build_status")],
        ])

        await message.answer(build_info, reply_markup=keyboard)

    async def cmd_apk(self, message: Message) -> None:
        """Handle /apk command - send Android APK file."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        from pathlib import Path
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        # Look for APK in common locations
        apk_paths = [
            Path("bin/everlay-2.0.0-arm64-v8a-debug.apk"),
            Path("bin/everlay-2.0.0-armeabi-v7a-debug.apk"),
            Path("bin/everlay-2.0.0-arm64-v8a-release.apk"),
            Path("bin/everlay-2.0.0-armeabi-v7a-release.apk"),
        ]

        apk_found = None
        for path in apk_paths:
            if path.exists():
                apk_found = path
                break

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Download APK", callback_data="download_apk")],
            [InlineKeyboardButton(text="🔨 Build APK (Linux/WSL)", callback_data="build_apk")],
            [InlineKeyboardButton(text="💻 Get Windows EXE", callback_data="download_exe")],
        ])

        if apk_found:
            size_mb = apk_found.stat().st_size / 1024 / 1024
            await message.answer(
                f"📱 **Android APK found** ({size_mb:.1f} MB)\n\n"
                f"Path: `{apk_found}`\n\n"
                f"Click button to download:",
                reply_markup=keyboard
            )
            await message.answer_document(
                document=str(apk_found),
                caption=f"Everlay AI v2.0.0 (Android)\n{apk_found.name}"
            )
        else:
            await message.answer(
                "❌ Android APK not found locally.\n\n"
                "**To build APK (Linux/WSL only):**\n"
                "1. Install WSL2: `wsl --install`\n"
                "2. In WSL: `sudo apt update && sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev automake`\n"
                "3. `pip install buildozer cython`\n"
                "4. `cd ~/everlay && export OPENROUTER_API_KEY=\"your-key\"`\n"
                "5. `buildozer -v android debug`\n\n"
                "**Or check GitHub Actions** for pre-built APKs.",
                reply_markup=keyboard
            )

    async def cmd_apkwindows(self, message: Message) -> None:
        """Handle /apkwindows command - send Windows EXE file."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        from pathlib import Path

        # Look for EXE in common locations
        exe_paths = [
            Path("dist/Everlay/Everlay.exe"),  # Actual build location
            Path("dist/Everlay.exe"),
            Path("build/Everlay/Everlay.exe"),
            Path("Everlay.exe"),
        ]

        exe_found = None
        for path in exe_paths:
            if path.exists():
                exe_found = path
                break

        # Create inline keyboard with options
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Download EXE", callback_data="download_exe")],
            [InlineKeyboardButton(text="🔨 Build EXE", callback_data="build_exe")],
            [InlineKeyboardButton(text="📱 Get APK", callback_data="download_apk")],
        ])

        if exe_found:
            size_mb = exe_found.stat().st_size / 1024 / 1024
            await message.answer(
                f"💻 **Windows EXE found** ({size_mb:.1f} MB)\n\n"
                f"Path: `{exe_found}`\n\n"
                f"Click button to download:",
                reply_markup=keyboard
            )
            # Send the file
            await message.answer_document(
                document=str(exe_found),
                caption=f"Everlay AI v2.0.0 (Windows)\n{exe_found.name}"
            )
        else:
            await message.answer(
                "❌ Windows EXE not found locally.\n\n"
                "**To build:**\n"
                "1. Run: `python build_exe.py` (Windows)\n"
                "2. Requires: `pip install pyinstaller`\n"
                "3. Output: `dist/Everlay/Everlay.exe`\n\n"
                "**Or download from GitHub Actions** (when available).",
                reply_markup=keyboard
            )

    async def cmd_build_status(self, message: Message) -> None:
        """Handle /build_status command - check GitHub Actions."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        import subprocess

        try:
            # Try to get latest workflow run from GitHub
            result = subprocess.run(
                ["gh", "run", "list", "--workflow=build-android.yml", "--limit=1", "--json=status,conclusion,createdAt,url"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                runs = json.loads(result.stdout)
                if runs:
                    run = runs[0]
                    status = run.get('status', 'unknown')
                    conclusion = run.get('conclusion', 'pending')
                    created = run.get('createdAt', '')
                    url = run.get('url', '')

                    status_emoji = {
                        'success': '✅',
                        'failure': '❌',
                        'cancelled': '⚠️',
                        'pending': '⏳',
                        'in_progress': '🔄'
                    }.get(conclusion, '❓')

                    await message.answer(
                        f"🏗 **Latest Build Status**\n\n"
                        f"Status: {status_emoji} {conclusion.title()}\n"
                        f"Workflow: Build Android APK\n"
                        f"Started: {created[:19].replace('T', ' ')}\n"
                        f"[View on GitHub]({url})"
                    )
                    return
        except Exception:
            pass

        await message.answer(
            "📋 **Build Status**\n\n"
            "GitHub CLI not available or no workflow runs.\n\n"
            "**To check manually:**\n"
            "1. Go to GitHub Actions tab\n"
            "2. Select 'Build Android APK' workflow\n"
            "3. Check latest run\n\n"
            "**To trigger build:**\n"
            "• Push to main branch\n"
            "• Create tag: `git tag v2.0.1 && git push --tags`\n"
            "• Manual trigger in Actions tab"
        )

    async def callback_download_apk(self, callback: CallbackQuery) -> None:
        """Handle APK download button."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return
        await callback.answer("📥 Sending APK...")
        await self.cmd_apk(callback.message)

    async def callback_download_exe(self, callback: CallbackQuery) -> None:
        """Handle EXE download button."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return
        await callback.answer("📥 Sending EXE...")
        await self.cmd_apkwindows(callback.message)

    async def callback_build_apk(self, callback: CallbackQuery) -> None:
        """Handle build APK button."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return
        await callback.answer("🔨 Build instructions...")
        await callback.message.answer(
            "🔨 **Build APK (Linux/WSL only)**\n\n"
            "**Quick start in WSL2:**\n"
            "```bash\n"
            "wsl --install\n"
            "# Restart, then in Ubuntu:\n"
            "sudo apt update && sudo apt install -y \\\n"
            "  git zip unzip openjdk-17-jdk python3-pip \\\n"
            "  autoconf libtool pkg-config zlib1g-dev \\\n"
            "  libncurses5-dev libncursesw5-dev libtinfo5 \\\n"
            "  cmake libffi-dev libssl-dev automake\n"
            "pip install buildozer cython\n"
            "cd ~/everlay\n"
            "export OPENROUTER_API_KEY=\"your-key\"\n"
            "buildozer -v android debug\n"
            "```\n\n"
            "**APK will be in:** `bin/everlay-2.0.0-arm64-v8a-debug.apk`"
        )

    async def callback_build_exe(self, callback: CallbackQuery) -> None:
        """Handle build EXE button."""
        if not self._is_allowed(callback.from_user.id):
            await callback.answer("❌ Access denied", show_alert=True)
            return
        await callback.answer("🔨 Build instructions...")
        await callback.message.answer(
            "🔨 **Build Windows EXE**\n\n"
            "**On Windows:**\n"
            "```cmd\n"
            "pip install pyinstaller\n"
            "python build_exe.py\n"
            "```\n\n"
            "**Output:** `dist/Everlay/Everlay.exe`\n\n"
            "**Requirements:**\n"
            "- Python 3.10+\n"
            "- PyInstaller\n"
            "- All dependencies from requirements.txt"
        )

    async def cmd_windows_exe(self, message: Message) -> None:
        """Handle /apkwindows command - send Windows EXE if available."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        from pathlib import Path

        # Check common build locations
        exe_paths = [
            Path("dist/Everlay.exe"),
            Path("build/Everlay/Everlay.exe"),
            Path("Everlay.exe"),
        ]

        exe_found = None
        for path in exe_paths:
            if path.exists():
                exe_found = path
                break

        if exe_found:
            size_mb = exe_found.stat().st_size / 1024 / 1024
            await message.answer(f"📦 Sending Windows EXE: {exe_found.name} ({size_mb:.1f} MB)")
            await message.answer_document(
                document=str(exe_found),
                caption=f"Everlay AI v2.0.0 (Windows)\n{exe_found.name}"
            )
        else:
            await message.answer(
                "❌ Windows EXE not found locally.\n\n"
                "**To build:**\n"
                "1. Run: `python build_exe.py` (Windows)\n"
                "2. Or use GitHub Actions:\n"
                "   - Push to main / create tag\n"
                "   - Download from Actions artifacts\n\n"
                "**Requirements:** PyInstaller, all dependencies"
            )

    async def handle_message(self, message: Message) -> None:
        """Handle regular messages."""
        if not self._is_allowed(message.from_user.id):
            await message.answer("❌ Access denied")
            return

        if not message.text:
            return

        session = self._get_session(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        session.message_count += 1

        agent = self._get_agent(session)

        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, "typing")

        try:
            # Run agent
            result = await agent.run(message.text, session.context)

            if result.success:
                # Split long messages
                content = result.content
                max_len = 4000
                for i in range(0, len(content), max_len):
                    chunk = content[i:i + max_len]
                    await message.answer(chunk)
            else:
                await message.answer(f"❌ Error: {result.error}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await message.answer(f"❌ Error: {e}")


# Global bot instance
_bot: Optional[TelegramBot] = None


def get_bot() -> TelegramBot:
    """Get or create global bot instance."""
    global _bot
    if _bot is None:
        _bot = TelegramBot()
    return _bot


async def run_bot() -> None:
    """Run the bot."""
    bot = get_bot()
    await bot.start()


async def stop_bot() -> None:
    """Stop the bot."""
    global _bot
    if _bot:
        await _bot.stop()
        _bot = None