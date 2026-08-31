import json
from typing import cast

import pytest

from app.api.errors import (
    ApiError,
    ApiErrorDetail,
    ErrorCodes,
    InvalidTriggerPayload,
    MorningNoteNotFound,
    PipelineError,
    _build_dict_of_lists,
    _json_response_from_api_error,
    translate,
)


class UnregisteredPipelineError(PipelineError):
    pass


def _det(api_error: ApiError) -> ApiErrorDetail:
    return cast(ApiErrorDetail, api_error.detail)


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_code"),
    [
        (MorningNoteNotFound(), 404, ErrorCodes.NO_ACTIVE_RUN),
        (InvalidTriggerPayload(), 422, ErrorCodes.INVALID_TRIGGER_PAYLOAD),
    ],
)
def test_translate_known_subclass_mapping(exc, expected_status, expected_code) -> None:
    api_error = translate(exc)

    assert isinstance(api_error, ApiError)
    assert api_error.status_code == expected_status
    assert _det(api_error).code == expected_code


def test_translate_default_logs_and_returns_500(caplog) -> None:
    exc = UnregisteredPipelineError("boom")

    api_error = translate(exc)

    assert api_error.status_code == 500
    assert _det(api_error).code == ErrorCodes.INTERNAL_ERROR
    assert "Unmapped PipelineError subclass escaped to HTTP boundary" in caplog.text
    assert any(rec.exc_type == "UnregisteredPipelineError" for rec in caplog.records)


def test_translate_base_pipeline_error_defaults_to_500(caplog) -> None:
    api_error = translate(PipelineError("bare"))

    assert api_error.status_code == 500
    assert _det(api_error).code == ErrorCodes.INTERNAL_ERROR


def test_build_dict_of_lists_groups_by_field() -> None:
    errors = [
        {"loc": ("body", "action"), "msg": "field required"},
        {"loc": ("body", "action"), "msg": "unexpected value"},
        {"loc": ("body", "justification"), "msg": "too short"},
    ]

    details = _build_dict_of_lists(errors)

    assert details == {
        "action": ["field required", "unexpected value"],
        "justification": ["too short"],
    }


def test_json_response_from_api_error_backfills_path_and_serializes_shape() -> None:
    api_error = ApiError(
        status_code=422,
        code=ErrorCodes.VALIDATION_ERROR,
        message="Validation error",
        details={"action": ["field required"]},
    )

    class FakeRequest:
        url = type("URL", (), {"path": "/morning-notes/n/1/feedback"})()

    response = _json_response_from_api_error(api_error, FakeRequest())

    body = json.loads(str(response.body, "utf-8"))
    assert response.status_code == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Validation error"
    assert body["details"] == {"action": ["field required"]}
    assert body["path"] == "/morning-notes/n/1/feedback"
    assert "timestamp" in body