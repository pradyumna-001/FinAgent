from datetime import datetime, timezone, timedelta
from app.utils.data_preprocessing import (
    is_data_fresh,
    check_confidence_threshold,
    generate_ingestion_flag,
    DataFlag
)

def test_data_freshness_check():
    """Verify that a timestamp older than 24 hours returns False, and recent returns True"""
    now = datetime.now(timezone.utc)

    recent_time = now - timedelta(hours=12)
    assert is_data_fresh(recent_time) is True

    stale_time = now - timedelta(hours=25)
    assert is_data_fresh(stale_time) is False

def test_confidence_threshold():
    """Verify that a confidence score below 0.75 triggers the low confidence flags"""
    low_score_res = check_confidence_threshold(0.74)
    assert low_score_res["low_confidence_flag"] is True
    assert low_score_res["action"] == "flag_for_review"

    high_score_res = check_confidence_threshold(0.75)
    assert high_score_res["low_confidence_flag"] is False
    assert high_score_res["action"] == "approve"

def test_dataflag_generation():
    """Verify that failed sources generate a DataFlag with accurate metadata structure"""
    source_name = "bloomberg_api"
    error_msg = "Rate limit exceeded"

    flag = generate_ingestion_flag(source=source_name, error_message=error_msg)

    assert isinstance(flag, DataFlag)
    assert flag.flag_type == "INGESTION_FAILURE"
    assert flag.source == source_name
    assert flag.metadata["error"] == error_msg
    assert isinstance(flag.timestamp, datetime)
    