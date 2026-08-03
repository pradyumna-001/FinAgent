import logging
from app.core.context import current_morning_note_id, current_pipeline_run_id


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.pipeline_run_id = current_pipeline_run_id.get()
        record.morning_note_id = current_morning_note_id.get()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(ContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s "
            "pipeline=%(pipeline_run_id)s "
            "note=%(morning_note_id)s "
            "%(name)s %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
