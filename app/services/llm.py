from app.core.config import settings
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError, AuthenticationError


NVIDIA_API_KEY = settings.NVIDIA_API_KEY
NVIDIA_BASE_URL = settings.NVIDIA_BASE_URL
NVIDIA_MODEL = settings.NVIDIA_MODEL
NVIDIA_FALLBACK_MODEL = settings.NVIDIA_FALLBACK_MODEL
NEMOTRON_MODEL = settings.NVIDIA_NEMOTRON_MODEL


client = AsyncOpenAI(
    api_key=NVIDIA_API_KEY,
    base_url=NVIDIA_BASE_URL,
)


async def summarize(system: str, user: str) -> str | None:
    infra_errors = (APIConnectionError, APITimeoutError, RateLimitError)
    messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
    ]

    try:
        resp = await client.chat.completions.create(model=NVIDIA_MODEL, messages=messages)  # type: ignore
        return resp.choices[0].message.content
    
    except infra_errors:
        try:
            resp = await client.chat.completions.create(model=NVIDIA_FALLBACK_MODEL, messages=messages)  # type: ignore
            return resp.choices[0].message.content
        except AuthenticationError:
            raise
        except Exception:
            return None


async def summarize_nemotron(system: str, user: str) -> str | None:
    infra_errors = (APIConnectionError, APITimeoutError, RateLimitError)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]

    try:
        resp = await client.chat.completions.create(model=NEMOTRON_MODEL, messages=messages)  # type: ignore[arg-type]
        return resp.choices[0].message.content

    except infra_errors:
        return None
