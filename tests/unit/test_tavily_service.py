import httpx
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.services.tavily import (
    TavilyArticle,
    TavilyConfigError,
    TavilyService,
)
from app.utils.flags import Severity


def _mock_client(response_json):
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_json
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    return mock_client


def _mock_client_raises(exc):
    mock_client = AsyncMock()
    mock_client.post.side_effect = exc
    mock_client.__aenter__.return_value = mock_client
    return mock_client


@pytest.mark.asyncio
async def test_search_happy_path_returns_typed_articles():
    payload = {"results": [{"title": "T", "content": "C", "url": "U"}]}
    s = TavilyService(api_key="fake")
    with patch("app.services.tavily.httpx.AsyncClient", return_value=_mock_client(payload)):
        r = await s.search("macro news Brazil", ["bcb.gov.br"], max_results=5)
    assert r.error is None
    assert len(r.articles) == 1
    assert isinstance(r.articles[0], TavilyArticle)
    assert r.articles[0] == TavilyArticle(title="T", content="C", url="U")


@pytest.mark.asyncio
async def test_search_empty_results_returns_empty_no_error():
    payload = {"results": []}
    s = TavilyService(api_key="fake")
    with patch("app.services.tavily.httpx.AsyncClient", return_value=_mock_client(payload)):
        r = await s.search("slow news day", [])
    assert r.articles == []
    assert r.error is None


@pytest.mark.asyncio
async def test_search_http_failure_returns_warning():
    s = TavilyService(api_key="fake")
    with patch("app.services.tavily.httpx.AsyncClient", return_value=_mock_client_raises(httpx.ConnectError("network down"))):
        r = await s.search("q", [])
    assert r.articles == []
    assert r.error is not None
    assert r.error.source == "tavily"
    assert r.error.severity == Severity.WARNING
    assert "network down" in r.error.message


@pytest.mark.asyncio
async def test_search_null_title_or_content_returns_fatal_with_query():
    payload = {"results": [{"title": None, "content": "good", "url": "u"}]}
    s = TavilyService(api_key="fake")
    with patch("app.services.tavily.httpx.AsyncClient", return_value=_mock_client(payload)):
        r = await s.search("PETR4 news Brazil", [])
    assert r.articles == []
    assert r.error is not None
    assert r.error.source == "tavily"
    assert r.error.severity == Severity.FATAL
    assert "PETR4 news Brazil" in r.error.message


@pytest.mark.asyncio
async def test_search_partial_null_articles_one_valid_one_invalid_returns_fatal():
    payload = {"results": [
        {"title": "valid", "content": "good", "url": "u"},
        {"title": None, "content": None, "url": None},
    ]}
    s = TavilyService(api_key="fake")
    with patch("app.services.tavily.httpx.AsyncClient", return_value=_mock_client(payload)):
        r = await s.search("q", [])
    assert r.error is not None
    assert r.error.severity == Severity.FATAL


def test_init_missing_key_raises_config_error():
    with pytest.raises(TavilyConfigError) as exc_info:
        TavilyService(api_key="")
    assert "TAVILY_API_KEY missing or empty" in str(exc_info.value)


def test_init_empty_key_from_settings_raises():
    with patch("app.services.tavily.settings.TAVILY_API_KEY", ""):
        with pytest.raises(TavilyConfigError):
            TavilyService()


def test_init_valid_key_does_not_read_settings():
    s = TavilyService(api_key="explicit")
    assert s.api_key == "explicit"
    assert s.timeout == 10.0


def test_init_explicit_timeout_overrides_default():
    s = TavilyService(api_key="explicit", timeout=30.0)
    assert s.timeout == 30.0
