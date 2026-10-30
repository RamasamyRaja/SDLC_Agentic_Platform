"""
Agent-layer exceptions.

Deliberately thin: nodes catch and re-signal existing M1-M5 exceptions
(NotFoundError, OwnershipError, LLMUnavailableError, etc.) through state
rather than inventing parallel exception types for the same failures — see
nodes.py. This module only adds what's genuinely new to this layer.
"""


class UnsupportedActionError(Exception):
    """The graph produced an AgentAction value the API/service layer does
    not know how to represent — should be unreachable in practice (the
    action enum is closed), kept as a defensive guard, never silently
    ignored."""
