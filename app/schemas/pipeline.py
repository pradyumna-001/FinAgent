from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TriggerRequest(BaseModel):
    manager_id: int
    portfolio_id: int


class TriggerResponse(BaseModel):
    pipeline_run_id: UUID = Field(default_factory=uuid4)
    morning_note_id: UUID = Field(default_factory=uuid4)
    portfolio_id: int
    tickers_count: int
    status: Literal["pending"] = "pending"
