from __future__ import annotations

import httpx
from dataclasses import dataclass

from app.core.config import settings
from app.utils.flags import DataFlag, Severity


class TavilyError(Exception):
    """Base for all TavilyService failures. Callers can `except TavilyError:` as catch-all."""


class TavilyConfigError(TavilyError):
    """Raised when the service cannot be constructed (e.g. missing API key)"""


class TavilyRequestError(TavilyError):
    """Internal: HTTP/network failure. Surfaced via TavilyResult.error, never raised across the boundary"""


class TavilyParseError(TavilyError):
    """Internal: bad response shape. Surfaced via TavilyResult.error, never raised across the boundary."""


@dataclass(frozen=True)
class TavilyArticle:
    title: str | None
    content: str | None
    url: str | None


@dataclass(frozen=True)
class TavilyResult:
    articles: list[TavilyArticle]
    error: DataFlag | None


class TavilyService:
    def __init__(self, api_key: str | None = None, timeout: float = 10.0) -> None:
        key = api_key if api_key is not None else settings.TAVILY_API_KEY
        if not key:
            raise TavilyConfigError("TAVILY_API_KEY missing or empty")
        self.api_key = key
        self.timeout = timeout

    async def search(
            self,
            query: str,
            include_domains: list[str],
            max_results: int = 10
    ) -> TavilyResult:
        payload = {
            "query": query,
            "max_results": max_results,
            "include_domains": include_domains
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            return TavilyResult(
                articles=[],
                error=DataFlag(
                    source="tavily",
                    severity=Severity.WARNING,
                    message=f"Tavily request error: {exc}"
                )
            )

        raw_articles = data.get("results") or []
        articles: list[TavilyArticle] = []
        for raw in raw_articles:
            if not isinstance(raw, dict):
                continue
            article = TavilyArticle(
                title=raw.get("title"),
                content=raw.get("content"),
                url=raw.get("url")
            )
            articles.append(article)

        if articles and any(a.title is None or a.content is None for a in articles):
            return TavilyResult(
                articles=[],
                error=DataFlag(
                    source="tavily",
                    severity=Severity.FATAL,
                    message=(
                        f"Tavily returned articles with null title/content for "
                        f"query {query!r} - schema may have changed"
                    )
                )
            )

        return TavilyResult(articles=articles, error=None)
    