from datetime import datetime

import pytest

from app.utils.flags import DataFlag, Severity


def test_dataflag_generation() -> None:
    flag = DataFlag(
        source="tavily", severity=Severity.WARNING, message="fetch failed: 500"
    )
    assert flag.source == "tavily"
    assert flag.severity is Severity.WARNING
    assert "fetch failed" in flag.message
    assert flag.is_warning() is True
    assert flag.is_fatal() is False


def test_dataflag_rejects_empty_source() -> None:
    with pytest.raises(ValueError, match="source must be non-empty"):
        DataFlag(source="", severity=Severity.INFO, message="x")


def test_dataflag_rejects_empty_message() -> None:
    with pytest.raises(ValueError, match="message must be non-empty"):
        DataFlag(source="tavily", severity=Severity.WARNING, message="")


def test_to_dict_serializes_datetime_as_iso_8601() -> None:
    before = datetime.now()
    flag = DataFlag(source="b3", severity=Severity.FATAL, message="stale")
    payload = flag.to_dict()
    after = datetime.now()

    assert payload["source"] == "b3"
    assert payload["severity"] == "fatal"
    assert payload["message"] == "stale"

    parsed = datetime.fromisoformat(payload["created_at"])
    assert before <= parsed <= after
