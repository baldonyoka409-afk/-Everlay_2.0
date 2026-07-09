"""
Agent base classes and management.
"""
import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from core.config import get_settings
from core.exceptions import AgentError, AgentTimeoutError
from core.logging_config import get_logger
from core.openrouter_client import Message, OpenRouterClient, ChatCompletion, ChatCompletionChunk, get_client

logger = get_logger(__name__)


class AgentStatus(Enum):
    """Agent status states."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentContext:
    """Execution context for an agent."""
    agent_id: str
    conversation_id: str
    user_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentResult:
    """Result of agent execution."""
    success: bool
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """Base class for agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON Schema for tool parameters."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool."""
        pass

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class BaseAgent(ABC):
    """
    Base class for all agents.

    Provides common functionality for OpenRouter-based agents with tool support.
    """

    def __init__(
        self,
        name: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Tool]] = None,
        client: Optional[OpenRouterClient] = None,
    ):
        self.name = name
        self.settings = get_settings()
        self.client = client or get_client()

        self.system_prompt = system_prompt or self.settings.agent_default_system_prompt
        self.model = model or self.settings.default_agent_model
        self.temperature = temperature if temperature is not None else self.settings.default_agent_temperature
        self.max_tokens = max_tokens or self.settings.default_agent_max_tokens

        self.tools: Dict[str, Tool] = {}
        if tools:
            for tool in tools:
                self.add_tool(tool)

        self._conversation_history: List[Message] = []
        self._status = AgentStatus.IDLE
        self._current_context: Optional[AgentContext] = None

    @property
    def status(self) -> AgentStatus:
        return self._status

    def add_tool(self, tool: Tool) -> None:
        """Register a tool."""
        self.tools[tool.name] = tool
        logger.debug(f"Agent {self.name}: added tool {tool.name}")

    def remove_tool(self, name: str) -> None:
        """Remove a tool."""
        self.tools.pop(name, None)

    def get_tools_openai_format(self) -> List[Dict[str, Any]]:
        """Get tools in OpenAI format."""
        return [tool.to_openai_format() for tool in self.tools.values()]

    def _build_messages(
        self,
        user_message: str,
        context: Optional[AgentContext] = None,
        include_history: bool = True,
    ) -> List[Message]:
        """Build message list for API call."""
        messages = []

        # System prompt
        messages.append(Message(role="system", content=self.system_prompt))

        # Conversation history
        if include_history and self._conversation_history:
            # Limit history
            max_history = self.settings.max_conversation_history
            history = self._conversation_history[-max_history:]
            messages.extend(history)

        # Current user message
        messages.append(Message(role="user", content=user_message))

        return messages

    async def _execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Message]:
        """Execute tool calls and return tool response messages."""
        tool_messages = []

        for tool_call in tool_calls:
            function = tool_call.get("function", {})
            tool_name = function.get("name")
            tool_args = function.get("arguments", {})

            if isinstance(tool_args, str):
                import json
                tool_args = json.loads(tool_args)

            tool = self.tools.get(tool_name)
            if not tool:
                error_msg = f"Tool not found: {tool_name}"
                logger.error(error_msg)
                tool_messages.append(Message(
                    role="tool",
                    content=error_msg,
                    tool_call_id=tool_call.get("id"),
                ))
                continue

            try:
                logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
                result = await tool.execute(**tool_args)
                tool_messages.append(Message(
                    role="tool",
                    content=str(result),
                    tool_call_id=tool_call.get("id"),
                ))
            except Exception as e:
                error_msg = f"Tool {tool_name} failed: {e}"
                logger.error(error_msg)
                tool_messages.append(Message(
                    role="tool",
                    content=error_msg,
                    tool_call_id=tool_call.get("id"),
                ))

        return tool_messages

    async def run(
        self,
        user_message: str,
        context: Optional[AgentContext] = None,
        stream: bool = False,
    ) -> Union[AgentResult, AsyncGenerator[AgentResult, None]]:
        """
        Run the agent with a user message.

        Args:
            user_message: User input
            context: Execution context
            stream: Whether to stream the response

        Returns:
            AgentResult or AsyncGenerator of AgentResult chunks
        """
        if context is None:
            context = AgentContext(
                agent_id=str(uuid.uuid4()),
                conversation_id=str(uuid.uuid4()),
            )

        self._current_context = context
        self._status = AgentStatus.RUNNING

        try:
            messages = self._build_messages(user_message, context)

            if stream:
                return self._run_stream(messages, context)
            else:
                return await self._run_single(messages, context)

        except Exception as e:
            self._status = AgentStatus.ERROR
            logger.error(f"Agent {self.name} error: {e}")
            return AgentResult(success=False, content="", error=str(e))

    async def _run_single(
        self,
        messages: List[Message],
        context: AgentContext,
    ) -> AgentResult:
        """Run single (non-streaming) completion."""
        tools = self.get_tools_openai_format() if self.tools else None

        response = await self.client.chat_completion(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tools=tools,
            tool_choice="auto" if tools else None,
        )

        # Handle tool calls
        if isinstance(response, ChatCompletion):
            choice = response.choices[0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                self._status = AgentStatus.WAITING_TOOL
                tool_messages = await self._execute_tool_calls(tool_calls)

                # Add assistant message with tool calls
                messages.append(Message(
                    role="assistant",
                    content=message.get("content", ""),
                    tool_calls=tool_calls,
                ))
                messages.extend(tool_messages)

                # Get final response
                final_response = await self.client.chat_completion(
                    messages=messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                if isinstance(final_response, ChatCompletion):
                    final_choice = final_response.choices[0]
                    final_content = final_choice.get("message", {}).get("content", "")

                    # Update history
                    self._conversation_history.append(Message(role="user", content=messages[-1].content))
                    self._conversation_history.append(Message(role="assistant", content=final_content))

                    self._status = AgentStatus.COMPLETED
                    return AgentResult(
                        success=True,
                        content=final_content,
                        tool_calls=tool_calls,
                        usage=final_response.usage,
                    )

            # No tool calls needed
            content = message.get("content", "")
            self._conversation_history.append(Message(role="user", content=messages[-1].content))
            self._conversation_history.append(Message(role="assistant", content=content))

            self._status = AgentStatus.COMPLETED
            return AgentResult(
                success=True,
                content=content,
                usage=response.usage,
            )

        self._status = AgentStatus.ERROR
        return AgentResult(success=False, content="", error="Unexpected response type")

    async def _run_stream(
        self,
        messages: List[Message],
        context: AgentContext,
    ) -> AsyncGenerator[AgentResult, None]:
        """Run streaming completion."""
        tools = self.get_tools_openai_format() if self.tools else None

        stream = await self.client.chat_completion(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tools=tools,
            tool_choice="auto" if tools else None,
            stream=True,
        )

        collected_content = ""
        collected_tool_calls: List[Dict[str, Any]] = []

        async for chunk in stream:
            if chunk.choices:
                choice = chunk.choices[0]
                delta = choice.get("delta", {})

                if delta.get("content"):
                    content = delta["content"]
                    collected_content += content
                    yield AgentResult(
                        success=True,
                        content=content,
                        metadata={"streaming": True, "complete": False},
                    )

                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        index = tc.get("index", 0)
                        while len(collected_tool_calls) <= index:
                            collected_tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if tc.get("id"):
                            collected_tool_calls[index]["id"] = tc["id"]
                        if tc.get("function", {}).get("name"):
                            collected_tool_calls[index]["function"]["name"] = tc["function"]["name"]
                        if tc.get("function", {}).get("arguments"):
                            collected_tool_calls[index]["function"]["arguments"] += tc["function"]["arguments"]

        # Handle tool calls if any
        if collected_tool_calls and any(tc.get("function", {}).get("name") for tc in collected_tool_calls):
            self._status = AgentStatus.WAITING_TOOL
            valid_tool_calls = [tc for tc in collected_tool_calls if tc.get("function", {}).get("name")]
            tool_messages = await self._execute_tool_calls(valid_tool_calls)

            messages.append(Message(
                role="assistant",
                content=collected_content,
                tool_calls=valid_tool_calls,
            ))
            messages.extend(tool_messages)

            # Stream final response
            final_stream = await self.client.chat_completion(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )

            final_content = ""
            async for chunk in final_stream:
                if chunk.choices:
                    choice = chunk.choices[0]
                    delta = choice.get("delta", {})
                    if delta.get("content"):
                        content = delta["content"]
                        final_content += content
                        yield AgentResult(
                            success=True,
                            content=content,
                            metadata={"streaming": True, "complete": False},
                        )

            self._conversation_history.append(Message(role="user", content=messages[-2].content))
            self._conversation_history.append(Message(role="assistant", content=final_content))
            self._status = AgentStatus.COMPLETED
            yield AgentResult(
                success=True,
                content=final_content,
                tool_calls=valid_tool_calls,
                metadata={"streaming": True, "complete": True},
            )
        else:
            self._conversation_history.append(Message(role="user", content=messages[-1].content))
            self._conversation_history.append(Message(role="assistant", content=collected_content))
            self._status = AgentStatus.COMPLETED
            yield AgentResult(
                success=True,
                content=collected_content,
                metadata={"streaming": True, "complete": True},
            )

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()
        logger.debug(f"Agent {self.name}: history cleared")

    def get_history(self) -> List[Message]:
        """Get conversation history."""
        return self._conversation_history.copy()

    async def close(self) -> None:
        """Clean up resources."""
        await self.client.close()