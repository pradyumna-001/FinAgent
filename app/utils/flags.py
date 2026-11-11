from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Severity(Enum):
    """Severity level for a DataFlag.

    INFO: informational, non-blocking.
    WARNING: degraded but pipeline continues.
    FATAL: blocking error that should halt or fail-visible.
    """

    INFO = "info"
    WARNING = "warning"
    FATAL = "fatal"


@dataclass(frozen=True)
class DataFlag:
    """A fail-visible data quality flag raised by a graph node.

    Attributes:
        source: Name of the node or component that raised the flag.
        severity: Severity level (INFO, WARNING, FATAL).
        message: Human-readable description of the issue.
        created_at: Timestamp when the flag was created.
    """

    source: str
    severity: Severity
    message: str
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Validate that source and message are non-empty."""
        if not self.source:
            raise ValueError("DataFlag.source must be non-empty")
        if not self.message:
            raise ValueError("DataFlag.message must be non-empty")

    def is_fatal(self) -> bool:
        """Return True if this flag's severity is FATAL."""
        return self.severity == Severity.FATAL

    def is_warning(self) -> bool:
        """Return True if this flag's severity is WARNING."""
        return self.severity == Severity.WARNING

    def to_dict(self) -> dict[str, object]:
        """Serialize this DataFlag to a plain dict for JSON/logging output."""
        return {
            "source": self.source,
            "severity": self.severity.value,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
        }
