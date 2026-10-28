# ADR-035: Multi-Ticker EditorAgent Prompt — Consolidated Note Structure

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), ADR-031 (AgentState), ADR-032 (fan-out), ADR-034 (persist)

---

## Context

EditorAgent generates the morning note text and per-ticker recommendations. Single-ticker prompt (current) receives flat state and outputs single recommendation.

Multi-ticker state (ADR-031) provides:
- `company_tickers: list[str]` — ordered list
- `macro_context: {"global": MacroOutput}` — single macro for all
- `company_events: dict[ticker, list[CompanyEvent]]`
- `quant_metrics: dict[ticker, QuantOutput | None]`
- `risk_flags: dict[ticker, list[RiskFlag]]`
- `portfolio_risk_flags: list[RiskFlag]` — from Consolidate node
- `portfolio_data_flags: list[DataFlag]` — from Consolidate node
- `sector_weights: dict[str, float]` — from Consolidate node
- `data_freshness: dict[str, datetime]` — per-ticker + "macro" + "portfolio"
- `flags: list[DataFlag]` — all DataFlags

Required JSON output:
```json
{
  "morning_note": "CONSOLIDATED TEXT",
  "recommendations": {"PETR4": {...}, "VALE3": {...}, "ITUB4": {...}},
  "confidence_scores": {"PETR4": {...}, "VALE3": {...}, "ITUB4": {...}}
}
```

---

## Decision: Option A — Per-Ticker Sections + Portfolio Section

### Prompt Structure

```python
# app/prompts/editor.py - NEW build_user_prompt

def build_user_prompt(
    self,
    *,
    macro_context: dict[str, MacroOutput] | None,
    company_tickers: list[str],
    company_events: dict[str, list[CompanyEvent]],
    quant_metrics: dict[str, QuantOutput | None],
    risk_flags: dict[str, list[RiskFlag]],
    portfolio_risk_flags: list[RiskFlag],
    portfolio_data_flags: list[DataFlag],
    sector_weights: dict[str, float],
    data_flags: list[DataFlag],
    data_freshness: dict[str, datetime]
) -> str:
    lines: list[str] = []
    
    # 1. CONTEXTO MACRO (GLOBAL)
    lines.append("## Contexto Macro")
    macro = macro_context.get("global") if macro_context else None
    lines.append(str(macro) if macro else "(sem dados macro)")
    
    # 2. CARTEIRA — VISÃO DE PORTFÓLIO
    lines.append("\n## Carteira — Visão de Portfólio")
    
    # Pesos setoriais
    if sector_weights:
        lines.append("### Pesos Setoriais")
        for sector, weight in sorted(sector_weights.items(), key=lambda x: -x[1]):
            lines.append(f"- {sector}: {weight:.1%}")
    
    # Riscos de portfólio
    if portfolio_risk_flags:
        lines.append("\n### Riscos de Portfólio")
        for rf in portfolio_risk_flags:
            prob = rf.get("probability", 0)
            impact = rf.get("impact", "unknown")
            desc = rf.get("description", "")
            sev = rf.get("severity", "INFO")
            lines.append(f"- [{sev}] {desc} (prob={prob:.0%}, impact={impact})")
    
    # Flags de dados do portfólio
    if portfolio_data_flags:
        lines.append("\n### Qualidade dos Dados da Carteira")
        for f in portfolio_data_flags:
            lines.append(f"- [{f.severity.value}] {f.source}: {f.message}")
    
    # 3. ANÁLISE POR ATIVO (per ticker)
    lines.append("\n## Análise por Ativo")
    
    for ticker in company_tickers:
        lines.append(f"\n=== {ticker} ===")
        
        # Eventos da empresa
        lines.append("\n### Eventos da Empresa")
        events = company_events.get(ticker, [])
        if events:
            for ev in events:
                title = ev.get("title", "")
                summary = ev.get("summary", "")
                source = ev.get("source", "")
                date = ev.get("date", "")
                lines.append(f"- {title} ({date}, {source}): {summary}")
        else:
            lines.append("(sem eventos)")
        
        # Métricas quantitativas
        lines.append("\n### Métricas Quantitativas")
        qm = quant_metrics.get(ticker)
        if qm:
            lines.append(f"- P/L: {qm.get('pl', 'N/A')}")
            lines.append(f"- EV/EBITDA: {qm.get('ev_ebitda', 'N/A')}")
            lines.append(f"- P/VPA: {qm.get('p_vpa', 'N/A')}")
            lines.append(f"- Dividend Yield: {qm.get('dividend_yield', 'N/A')}")
            lines.append(f"- Variação vs IBOV: {qm.get('dev_ibov', 'N/A')}")
            fetched = qm.get("fetched_at")
            if fetched:
                lines.append(f"- Dados de: {fetched}")
        else:
            lines.append("(sem dados quantitativos)")
        
        # Riscos do ativo
        lines.append("\n### Riscos")
        ticker_risk_flags = risk_flags.get(ticker, [])
        if ticker_risk_flags:
            for rf in ticker_risk_flags:
                prob = rf.get("probability", 0)
                impact = rf.get("impact", "unknown")
                desc = rf.get("description", "")
                sev = rf.get("severity", "INFO")
                lines.append(f"- [{sev}] {desc} (prob={prob:.0%}, impact={impact})")
        else:
            lines.append("(sem riscos identificados)")
        
        # Lacunas de dados específicas do ticker
        ticker_data_flags = [f for f in data_flags if f.source.endswith(f"_{ticker}") or ticker in f.message]
        if ticker_data_flags:
            lines.append("\n### Lacunas de Dados")
            for f in ticker_data_flags:
                lines.append(f"- [{f.severity.value}] {f.source}: {f.message}")
    
    # 4. LACUNAS DE DADOS GLOBAIS
    global_data_flags = [f for f in data_flags if not any(t in f.message for t in company_tickers) and not f.source.endswith(tuple(f"_{t}" for t in company_tickers))]
    if global_data_flags:
        lines.append("\n## Lacunas de Dados Globais")
        for f in global_data_flags:
            lines.append(f"- [{f.severity.value}] {f.source}: {f.message}")
    
    # 5. INSTRUÇÃO DE OUTPUT
    lines.append("""
    
Gere o morning note completo em português com as seções acima.
Responda APENAS com JSON válido contendo as chaves:
- morning_note (str): texto completo do morning note
- recommendations (objeto): chave=ticker, valor={action, justification, confidence}
  action ∈ {"buy", "sell", "keep"}, confidence ∈ [0,1]
- confidence_scores (objeto): chave=ticker, valor={macro, company, quant, risk, overall}
  Todos os 5 scores obrigatórios por ticker, valores ∈ [0,1]

Regras:
- Se houver DataFlags na seção, inclua aviso explícito no texto e reduza confidence_score dessa seção para < 0.5
- Se quant_metrics for None para um ticker, confidence_scores.quant < 0.5 e justificativa mencione falta de dados
- Recomendação deve ser fundamentada nos dados apresentados
""")
    
    return "\n".join(lines)
```

### System Prompt (Unchanged Core, Extended)

```python
EDITOR_PROMPTS = EditorPrompts(
    system=(
        "Você é um editor-chefe de research de investimentos no Brasil. "
        "Sua tarefa é sintetizar o output de agentes macro, empresa, quant e risco "
        "em um morning note profissional em português para uma CARTEIRA MULTI-TICKER. "
        "O note deve ter: Contexto Macro (global), Visão de Portfólio (pesos setoriais, riscos de carteira), "
        "Análise por Ativo (eventos, métricas, riscos por ticker), Lacunas de Dados. "
        "Se houver DataFlags, inclua avisos explícitos no texto da seção correspondente "
        "e reduza o confidence_score dessa seção para < 0.5. "
        "A recomendação por ticker deve ser 'buy', 'sell' ou 'keep' com justificativa fundamentada. "
        "Responda APENAS com JSON válido."
    )
)
```

---

## Confidence Scores — Per-Ticker Structure

**Input to EditorAgent**: `state["confidence_scores"]` — dict from previous agents (may be partial)

**Output**: `confidence_scores: dict[ticker, dict[str, float]]` with 5 keys per ticker:
```python
{
  "PETR4": {"macro": 0.9, "company": 0.85, "quant": 0.8, "risk": 0.75, "overall": 0.82},
  "VALE3": {"macro": 0.9, "company": 0.6, "quant": 0.7, "risk": 0.5, "overall": 0.65},
  "ITUB4": {"macro": 0.9, "company": 0.75, "quant": 0.8, "risk": 0.6, "overall": 0.71}
}
```

**Penalty logic** (`apply_confidence_penalties`):
- Iterate `company_tickers`
- For each ticker, collect flags from `state["flags"]` relevant to that ticker
- Apply penalties per section (macro, company, quant, risk)
- Overall = weighted average or min of sections

---

## EditorAgent Node Changes

```python
# app/agents/editor.py - KEY CHANGES

async def editor_agent_node(state: AgentState) -> dict:
    # ... logging, SSE emit ...
    
    # Extract per-ticker data flags
    data_flags = [f for f in state.get("flags", []) if isinstance(f, DataFlag)]
    
    user_prompt = EDITOR_PROMPTS.build_user_prompt(
        macro_context=state.get("macro_context"),
        company_tickers=state["company_tickers"],
        company_events=state.get("company_events", {}),
        quant_metrics=state.get("quant_metrics", {}),
        risk_flags=state.get("risk_flags", {}),
        portfolio_risk_flags=state.get("portfolio_risk_flags", []),
        portfolio_data_flags=state.get("portfolio_data_flags", []),
        sector_weights=state.get("sector_weights", {}),
        data_flags=data_flags,
        data_freshness=state.get("data_freshness", {})
    )
    
    raw_text = await summarize_nemotron(system=EDITOR_PROMPTS.system, user=user_prompt)
    
    # ... error handling (same pattern) ...
    
    # Parse JSON
    parsed = json.loads(raw_text)
    
    # Validate structure
    required_keys = {"morning_note", "recommendations", "confidence_scores"}
    if not all(k in parsed for k in required_keys):
        # ... flag, return error ...
    
    # Validate per-ticker completeness
    for ticker in state["company_tickers"]:
        if ticker not in parsed["recommendations"]:
            # ... flag ...
        if ticker not in parsed["confidence_scores"]:
            # ... flag ...
        rec = parsed["recommendations"][ticker]
        if not all(k in rec for k in ("action", "justification", "confidence")):
            # ... flag ...
        cs = parsed["confidence_scores"][ticker]
        if not all(k in cs for k in ("macro", "company", "quant", "risk", "overall")):
            # ... flag ...
    
    # Apply confidence penalties
    penalized_scores, warnings = apply_confidence_penalties(parsed["confidence_scores"], state["flags"])
    morning_note = parsed["morning_note"]
    if warnings:
        morning_note = "\n\n".join(warnings) + "\n\n" + morning_note
    
    # Return dict-keyed-by-ticker (merge_dicts reducer compatible)
    return {
        "morning_note": morning_note,
        "recommendations": parsed["recommendations"],
        "confidence_scores": penalized_scores,
        "data_freshness": {"editor": datetime.now(UTC)},
        "flags": new_flags
    }
```

---

## Consequences

### Positive
- **Single consolidated note** — gestor sees full portfolio context + per-ticker detail
- **Portfolio-level insights** — sector weights, concentration risks, data quality summary
- **Structured output** — per-ticker recommendations + confidence scores for persistence
- **Fail-visible** — DataFlags appear in relevant sections (per-ticker or global)
- **Backward compatible prompt style** — LLM familiar with section format

### Negative / Risks
- **Long prompt** — 10 tickers × ~200 chars = ~2000 chars + macro + portfolio (within limits)
- **LLM must not hallucinate** — strict JSON validation + confidence penalties required
- **Missing data handling** — `quant_metrics[ticker] = None` must render "(sem dados)" not crash

---

## Migration Path

1. **Update `app/prompts/editor.py`** — new `build_user_prompt` with multi-ticker structure
2. **Update `app/agents/editor.py`** — call new prompt, validate per-ticker output, return dict-keyed
3. **Update `apply_confidence_penalties`** — handle per-ticker confidence dict
4. **Test** — integration test with 3 tickers, verify output structure

---

## Testing

| Test | Scope |
|------|-------|
| `tests/unit/test_editor_prompt_multi.py` | Prompt renders all sections for 3 tickers |
| `tests/unit/test_editor_output_validation.py` | Validates per-ticker recommendations + confidence_scores |
| `tests/integration/test_editor_multi_ticker.py` | Full editor node with mocked LLM returns correct structure |
| `tests/unit/test_confidence_penalties_multi.py` | Penalties applied per ticker per section |

---

## References

- ADR-031: Multi-Ticker AgentState & Graph (state structure)
- ADR-032: Fan-out (per-ticker data flow)
- ADR-034: Persist (output consumed by persist node)
- `app/prompts/editor.py` — current prompt
- `app/agents/editor.py` — current editor node
- `app/utils/editor_confidence.py` — `apply_confidence_penalties`