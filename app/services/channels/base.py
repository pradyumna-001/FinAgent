"""Transport-agnostic channel protocol for recommendation delivery."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NotePayload:
    """Everything a channel needs to render a morning note for approval."""

    pipeline_run_id: str
    recommendation_id: int
    ticker: str
    action: str
    confidence: float
    justification: str


class Channel(Protocol):
    """Delivery channel seam. Telegram is the first impl; webhook can follow."""

    async def send_note(self, payload: NotePayload) -> None:
        """Deliver the note. Raises ChannelError subclasses on failure."""
        ...

    async def await_decision(
        self, run_id: str, rec_id: int, timeout: float
    ) -> bool | None:
        """Wait up to `timeout` seconds for a decision.

        Returns True=approved, False=rejected, None=timeout/no decision.
        """
        ...
