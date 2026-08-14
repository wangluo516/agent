class DomainError(Exception):
    """Base class for controlled domain failures."""


class ValidationError(DomainError):
    """Raised when a business rule rejects otherwise shaped data."""


class AttendeeBusyError(ValidationError):
    """Raised when one or more requested attendees are busy."""

    def __init__(self, attendee_ids: tuple[str, ...]) -> None:
        self.attendee_ids = attendee_ids
        super().__init__("one or more attendees are busy")


class AuthorizationError(DomainError):
    """Raised when an actor lacks permission for an operation."""


class ConflictError(DomainError):
    """Raised when an optimistic write cannot be applied."""
