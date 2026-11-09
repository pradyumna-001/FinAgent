from dataclasses import dataclass
from datetime import datetime

from app.graph.state import CompanyEvent, MacroOutput, QuantOutput, RiskFlag
from app.utils.flags import DataFlag


@dataclass(frozen=True)
class EditorPrompts:
    system: str

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
        """Build the EditorAgent user prompt for multi-ticker morning notes.

        Renders: Contexto Macro (global), Carteira (portfolio-level sector weights,
        risks, data flags), Análise por Ativo (per-ticker events, metrics, risks,
        data gaps), Lacunas de Dados Globais, and output instructions.

        Args:
            macro_context: Dict keyed by ticker, typically {"global": MacroOutput}.
            company_tickers: Ordered list of tickers to analyze.
            company_events: Dict[ticker, list[CompanyEvent]].
            quant_metrics: Dict[ticker, QuantOutput | None].
            risk_flags: Dict[ticker, list[RiskFlag]].
            portfolio_risk_flags: Portfolio-level risk flags from Consolidate node.
            portfolio_data_flags: Portfolio-level data flags from Consolidate node.
            sector_weights: Dict[sector, weight] from Consolidate node.
            data_flags: All DataFlags from upstream agents.
            data_freshness: Dict[ticker | "macro" | "portfolio", datetime].

        Returns:
            Formatted prompt string for the LLM.
        """
        lines: list[str] = []

        lines.append("## Contexto Macro")
        macro = macro_context.get("global") if macro_context else None
        lines.append(str(macro) if macro else "(sem dados macro)")

        lines.append("\n## Carteira — Visão de Portfólio")

        if sector_weights:
            lines.append("### Pesos Setoriais")
            for sector, weight in sorted(sector_weights.items(), key=lambda x: -x[1]):
                lines.append(f"- {sector}: {weight:.1%}")

        if portfolio_risk_flags:
            lines.append("\n### Riscos de Portfólio")
            for rf in portfolio_risk_flags:
                prob = rf.get("probability", 0)
                impact = rf.get("impact", "unknown")
                desc = rf.get("description", "")
                sev = rf.get("severity", "INFO")
                lines.append(f"- [{sev}] {desc} (prob={prob:.0%}, impact={impact})")

        if portfolio_data_flags:
            lines.append("\n### Qualidade dos Dados da Carteira")
            for f in portfolio_data_flags:
                lines.append(f"- [{f.severity.value}] {f.source}: {f.message}")

        lines.append("\n## Análise por Ativo")

        for ticker in company_tickers:
            lines.append(f"\n=== {ticker} ===")

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

            ticker_data_flags = [
                f for f in data_flags
                if ticker in f.message or f.source.endswith(f"_{ticker}")
            ]
            if ticker_data_flags:
                lines.append("\n### Lacunas de Dados")
                for f in ticker_data_flags:
                    lines.append(f"- [{f.severity.value}] {f.source}: {f.message}")

        global_data_flags = [
            f for f in data_flags
            if not any(t in f.message for t in company_tickers)
            and not f.source.endswith(tuple(f"_{t}" for t in company_tickers))
        ]
        if global_data_flags:
            lines.append("\n## Lacunas de Dados Globais")
            for f in global_data_flags:
                lines.append(f"- [{f.severity.value}] {f.source}: {f.message}")

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
