class NexoraError(Exception):
    """Base exception for expected application errors."""


class InvalidUserIdError(NexoraError):
    """Raised when a user ID is not a positive integer."""


class UserNotFoundError(NexoraError):
    """Raised when a requested user does not exist."""


class UserAlreadyExistsError(NexoraError):
    """Raised when attempting to create a user with an existing email."""
