from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    FATAL = "fatal"


@dataclass(frozen=True)
class DataFlag:
    source: str
    severity: Severity
    message: str
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("DataFlag.source must be non-empty")
        if not self.message:
            raise ValueError("DataFlag.message must be non-empty")

    def is_fatal(self) -> bool:
        return self.severity == Severity.FATAL

    def is_warning(self) -> bool:
        return self.severity == Severity.WARNING

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "severity": self.severity.value,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
        }
