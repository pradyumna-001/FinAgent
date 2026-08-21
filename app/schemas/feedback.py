from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import FeedbackAction


class FeedbackCreate(BaseModel):
    action: FeedbackAction
    justification: str
    comment: str | None = Field(default=None)


class FeedbackResponse(BaseModel):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
