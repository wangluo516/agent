class DomainError(Exception):
    """Base class for controlled domain failures."""


class ValidationError(DomainError):
    """Raised when a business rule rejects otherwise shaped data."""


class AuthorizationError(DomainError):
    """Raised when an actor lacks permission for an operation."""


class ConflictError(DomainError):
    """Raised when an optimistic write cannot be applied."""
