from datetime import datetime, timedelta


def is_data_fresh(source: str, fetched_at: datetime, *, now: datetime | None = None, max_age: timedelta = timedelta(hours=24)) -> bool:
    if now is None:
        now = datetime.now()
    return (now - fetched_at) <= max_age
