from contextvars import ContextVar


current_pipeline_run_id: ContextVar[str | None] = ContextVar("current_pipeline_run_id", default=None)
current_morning_note_id: ContextVar[str | None] = ContextVar("current_morning_note_id", default=None)
