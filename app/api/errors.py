class PipelineError(Exception):
    """Base for all pipeline-domain errors.

    Callers should catch this base for catch-all handling and discriminate on
    subclasses (e.g., MorningNoteNotFound) for retry or HTTP routing.
    """


class MorningNoteNotFound(PipelineError):
    """Raised when a morning note id does not resolve to a row"""


class InvalidTriggerPayload(PipelineError):
    """Raised when the trigger request fails semantic validation beyond 
    pydantic's structural checks (e.g., company_id not in manager's book).
    """

class InvalidTokenError(Exception):
    def __init__(self, message: str = "Invalid or expired token"):
        self.message = message
        super().__init__(self.message)