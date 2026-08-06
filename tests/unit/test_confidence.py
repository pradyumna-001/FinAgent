from app.utils.confidence import confidence_flag


def test_confidence_threshold() -> None:
    assert confidence_flag(0.5) is True
    assert confidence_flag(0.75) is True
    assert confidence_flag(0.9) is False
