# ADR 010: NVIDIA NIM as Primary LLM Provider

## Status
Accepted (2026-08-11)

## Context
LLM provider options for agent reasoning:
1. **OpenAI GPT-4o** — Best quality; expensive; rate limits
2. **Anthropic Claude** — Good quality; different API
3. **NVIDIA NIM (Nemotron 3 Ultra)** — OpenAI-compatible API; self-hosted option; cost-effective
4. **Local models (Ollama, vLLM)** — Full control; infrastructure overhead

## Decision
Use **NVIDIA NIM** as primary LLM provider via OpenAI-compatible API:
- **Base URL**: `https://integrate.api.nvidia.com/v1`
- **Primary model**: `openai/gpt-oss-20b` (configurable via `NVIDIA_MODEL`)
- **Fallback model**: `openai/gpt-oss-20b` (configurable via `NVIDIA_FALLBACK_MODEL`)
- **Nemotron 3 Ultra**: `nvidia/nemotron-3-ultra` for EditorAgent (via `NVIDIA_NEMOTRON_MODEL`)

Configuration in `app/core/config.py`:
```python
NVIDIA_API_KEY: str
NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL: str = "openai/gpt-oss-20b"
NVIDIA_FALLBACK_MODEL: str = "openai/gpt-oss-20b"
NVIDIA_NEMOTRON_MODEL: str = "nvidia/nemotron-3-ultra"
```

Client in `app/services/llm.py`:
- `summarize()` — primary + fallback for Macro/Company/Risk agents
- `summarize_nemotron()` — single-model for EditorAgent (Nemotron 3 Ultra)

## Rationale
- **OpenAI-compatible** — Drop-in replacement; minimal code changes
- **Cost** — NIM pricing competitive for volume
- **Fallback built-in** — Client tries primary, falls back automatically
- **No vendor lock-in** — Can swap to self-hosted NIM or other OpenAI-compatible endpoint
- **Nemotron for generation** — Nemotron 3 Ultra optimized for structured output (JSON)

## Consequences
- **Positive**: Cost-effective, flexible, OpenAI-compatible
- **Negative**: Rate limits on NVIDIA hosted NIM; quality slightly below GPT-4o for complex reasoning
- **Risk**: API changes; mitigation: abstraction layer in `app/services/llm.py`

## Deviations Noted
- Issue #77 (RiskAgent) specified "GPT-4o for complex reasoning" — implementation uses NIM (flagged in PR #78)
- EditorAgent uses Nemotron 3 Ultra without fallback (single-model call per spec)

## Implementation Notes
- `app/services/llm.py` wraps OpenAI client with NIM config
- Fallback logic: on 429/5xx, retry once with fallback model
- All agent tests mock `summarize` / `summarize_nemotron` (no real API calls in CI)