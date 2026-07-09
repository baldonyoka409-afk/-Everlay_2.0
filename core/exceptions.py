"""
Custom exceptions for Everlay.
"""


class EverlayError(Exception):
    """Base exception for Everlay errors."""
    pass


class ConfigurationError(EverlayError):
    """Configuration related errors."""
    pass


class AgentError(EverlayError):
    """Agent execution errors."""
    pass


class AgentTimeoutError(AgentError):
    """Agent execution timeout."""
    pass


class AgentModelError(AgentError):
    """Model-related errors (rate limits, invalid model, etc.)."""
    pass


class AgentToolError(AgentError):
    """Tool execution errors."""
    pass


class TelegramError(EverlayError):
    """Telegram bot errors."""
    pass


class DatabaseError(EverlayError):
    """Database related errors."""
    pass


class ValidationError(EverlayError):
    """Validation errors."""
    pass