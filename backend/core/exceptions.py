class NexoraError(Exception):
    """Base exception for expected application errors."""


class InvalidUserIdError(NexoraError):
    """Raised when a user ID is not a positive integer."""


class UserNotFoundError(NexoraError):
    """Raised when a requested user does not exist."""


class UserAlreadyExistsError(NexoraError):
    """Raised when attempting to create a user with an existing email."""


class InvalidCredentialsError(NexoraError):
    """Raised when authentication credentials are invalid."""


class OrganizationNotFoundError(NexoraError):
    """Raised when an organization does not exist."""


class OrganizationMembershipRequiredError(NexoraError):
    """Raised when a user is not a member of an organization."""


class OrganizationAccessDeniedError(NexoraError):
    """Raised when a user lacks sufficient organization privileges."""


class OrganizationMembershipAlreadyExistsError(NexoraError):
    """Raised when a user is already a member of an organization."""


class DocumentNotFoundError(NexoraError):
    """Raised when a requested document does not exist."""

class InvalidDocumentUploadError(NexoraError):
    """Raised when an uploaded document is invalid."""


class DocumentUploadFailedError(NexoraError):
    """Raised when document storage/finalization fails."""

class InvalidDocumentUploadError(NexoraError):
    """Raised when an uploaded document is invalid."""


class DocumentUploadFailedError(NexoraError):
    """Raised when document storage/finalization fails."""

class DocumentExtractionError(NexoraError):
    """Raised when document text extraction fails."""
