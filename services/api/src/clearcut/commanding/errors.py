"""Typed, safe errors for the governed-command kernel.

Every error crossing the kernel's public boundary is a typed
:class:`GovernedCommandError` carrying a stable machine ``code`` and a neutral,
human-safe ``message``. Messages deliberately never embed tenant identifiers,
foreign-resource identity, or "exists but denied" hints, so that a caller in
one tenant cannot probe for the existence of another tenant's resources.
Callers branch on ``code``; they never parse ``message``.
"""

from __future__ import annotations


class GovernedCommandError(RuntimeError):
    """Base class for all typed governed-command failures.

    Subclasses set a class-level ``code`` and a neutral default ``message``.
    The ``message`` may be overridden with caller-supplied text only for
    validation, where the text is already sanitized by the kernel; it is never
    used to convey foreign-resource details.
    """

    code: str = "governed_command_error"
    _default_message: str = "The governed command could not be processed."

    def __init__(self, message: str | None = None) -> None:
        resolved = message if message else self._default_message
        super().__init__(resolved)
        self.message: str = resolved


class CommandValidationError(GovernedCommandError):
    """The command envelope or its inputs are malformed."""

    code = "command_validation_failed"
    _default_message = "The command inputs were invalid."


class CommandForbiddenError(GovernedCommandError):
    """The actor lacks the capability to perform the command in this scope."""

    code = "command_forbidden"
    _default_message = "This action is not permitted."


class CommandNotFoundError(GovernedCommandError):
    """The targeted resource is not visible in the authenticated scope.

    Presented with the same neutral shape as :class:`CommandForbiddenError`
    (distinct code, no foreign detail) so callers can map both to a single safe
    client response without revealing whether a resource exists.
    """

    code = "command_not_found"
    _default_message = "The requested resource was not found."


class StaleVersionConflictError(GovernedCommandError):
    """The caller's expected version no longer matches the current aggregate."""

    code = "stale_version_conflict"
    _default_message = "The resource changed since it was last loaded."


class IdempotencyIntentConflictError(GovernedCommandError):
    """The idempotency key was reused with a different intent."""

    code = "idempotency_intent_conflict"
    _default_message = "The idempotency key was reused with a different request."


__all__ = [
    "GovernedCommandError",
    "CommandValidationError",
    "CommandForbiddenError",
    "CommandNotFoundError",
    "StaleVersionConflictError",
    "IdempotencyIntentConflictError",
]
