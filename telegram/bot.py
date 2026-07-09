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
        self.router.callback_query(F.data.startswith("agent_"))(self.callback_agent)
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