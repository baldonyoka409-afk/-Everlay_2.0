"""
Pre-configured agent implementations.
"""
from typing import List, Optional

from agents.base import BaseAgent, Tool
from agents.tools import get_builtin_tools
from core.config import get_settings
from core.openrouter_client import OpenRouterClient


# All available tools for full-featured agents
ALL_TOOLS = ["read_file", "write_file", "list_files", "shell", "python", "web_search", "http_request", "json_tool", "search_files", "web_scrape", "git", "database", "csv_tool", "rag", "code_interpreter", "resource_monitor", "model_router"]
# Coding-focused tools (no web search to avoid distractions)
CODE_TOOLS = ["read_file", "write_file", "list_files", "shell", "python", "search_files", "git", "json_tool", "rag", "code_interpreter", "resource_monitor"]
# Chat-only tools (minimal)
CHAT_TOOLS = ["model_router"]


class DefaultAgent(BaseAgent):
    """
    General-purpose agent with all tools.
    """

    def __init__(
        self,
        name: str = "default",
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Tool]] = None,
        client: Optional[OpenRouterClient] = None,
    ):
        settings = get_settings()

        default_prompt = """You are a helpful AI assistant with access to a wide range of tools.

Available tools:
- File operations: read, write, list files
- Shell commands and Python execution
- Web search and scraping
- HTTP requests to APIs
- JSON parsing and manipulation
- File content search (grep-like)
- Git operations
- SQLite database queries
- CSV file processing

Use these tools to help the user accomplish their tasks. Be concise and practical."""

        super().__init__(
            name=name,
            system_prompt=system_prompt or default_prompt,
            model=model or settings.default_agent_model,
            temperature=temperature if temperature is not None else settings.default_agent_temperature,
            max_tokens=max_tokens or settings.default_agent_max_tokens,
            tools=tools or get_builtin_tools(ALL_TOOLS),
            client=client,
        )


class CodeAgent(BaseAgent):
    """
    Specialized agent for coding tasks.
    """

    def __init__(
        self,
        name: str = "code",
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Tool]] = None,
        client: Optional[OpenRouterClient] = None,
    ):
        settings = get_settings()

        default_prompt = """You are an expert software engineer. You help with:
- Writing, reading, and modifying code
- Debugging and fixing bugs
- Code reviews and refactoring
- Architecture and design decisions
- Testing and deployment

Best practices:
- Write clean, maintainable code
- Follow existing code style and patterns
- Add appropriate comments and documentation
- Handle errors gracefully
- Write tests when appropriate

Available tools:
- File operations: read, write, list files
- Shell commands and Python execution
- File content search (grep-like)
- Git operations
- JSON parsing

Use the available tools to explore the codebase, make changes, and verify your work."""

        super().__init__(
            name=name,
            system_prompt=system_prompt or default_prompt,
            model=model or settings.default_agent_model,
            temperature=temperature if temperature is not None else 0.3,  # Lower temp for code
            max_tokens=max_tokens or settings.default_agent_max_tokens,
            tools=tools or get_builtin_tools(CODE_TOOLS),
            client=client,
        )


class ChatAgent(BaseAgent):
    """
    Simple conversational agent without tools.
    """

    def __init__(
        self,
        name: str = "chat",
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Tool]] = None,
        client: Optional[OpenRouterClient] = None,
    ):
        settings = get_settings()

        default_prompt = """You are a friendly, helpful AI assistant. Engage in natural conversation with the user.
Be concise but thorough. Ask clarifying questions when needed."""

        super().__init__(
            name=name,
            system_prompt=system_prompt or default_prompt,
            model=model or settings.default_agent_model,
            temperature=temperature if temperature is not None else 0.8,
            max_tokens=max_tokens or settings.default_agent_max_tokens,
            tools=tools or [],  # No tools for pure chat
            client=client,
        )


# Agent factory
class AgentFactory:
    """Factory for creating agents."""

    _registry = {
        "default": DefaultAgent,
        "code": CodeAgent,
        "chat": ChatAgent,
    }

    @classmethod
    def register(cls, name: str, agent_class: type) -> None:
        """Register a custom agent type."""
        cls._registry[name] = agent_class

    @classmethod
    def create(cls, agent_type: str, **kwargs) -> BaseAgent:
        """Create an agent by type."""
        agent_class = cls._registry.get(agent_type)
        if not agent_class:
            raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(cls._registry.keys())}")
        return agent_class(**kwargs)

    @classmethod
    def list_types(cls) -> List[str]:
        """List available agent types."""
        return list(cls._registry.keys())