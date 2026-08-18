from dataclasses import dataclass

from app.graph.state import MacroOutput, CompanyEvent, QuantOutput, RiskFlag
from app.utils.flags import DataFlag


@dataclass(frozen=True)
class EditorPrompts:
    system: str

    def build_user_prompt(  # type: ignore[return]
            self,
            *,
            macro_context: MacroOutput | None,
            company_events: list[CompanyEvent],
            quant_metrics: QuantOutput | None,
            risk_flags: list[RiskFlag],
            data_flags: list[DataFlag]
    ) -> str:
        lines: list[str] = []
        lines.append("## Contexto Macro")
        lines.append(str(macro_context) if macro_context else "(sem dados)")
        lines.append("\n## Eventos da Empresa")
        for ev in company_events:
            lines.append(f"- {ev.get('title', '')}: {ev.get('summary', '')}")
            if not company_events:
                lines.append("(sem eventos)")
            lines.append("\n## Métricas Quantitativas")
            lines.append(str(quant_metrics) if quant_metrics else "(sem dados)")
            lines.append("\n## Riscos Identificados")
            for rf in risk_flags:
                lines.append(
                    f"- probl={rf.get('probability')}, impact={rf.get('impact')}"
                    f"- desc={rf.get('description')}, severity={rf.get('severity')}"
                )
            if not risk_flags:
                lines.append("(sem riscos)")
            if data_flags:
                lines.append("\n## Lacunas de Dados (DataFlags)")
                for f in data_flags:
                    lines.append(f"- [{f.severity.value}] {f.source}: {f.message}")

            lines.append(
                "\n\nGere o morning note completo em português com as seções: "
                "Contexto Macro, Eventos, Métricas, Riscos, Recomendação. "
                "Responda APENAS com JSON válido contendo as chaves: "
                "morning_note (str), recommendation (objeto com action, justification, confidence), "
                "confidence_scores (objeto com macro, company, quant, risk, overall)."
            )

            return "\n".join(lines)


EDITOR_PROMPTS = EditorPrompts(
    system=(
        "Você é um editor-chefe de research de investimentos no Brasil. "
        "Sua tarefa é sintetizar o output de agentes macro, empresa, quant e risco "
        "em um morning note profissional em português. "
        "Se houver DataFlags, incla avisos explícitos no texto da seção correspondente "
        "e reduza o confidence_score dessa seção para < 0.5. "
        "A recomendação deve ser 'buy', 'sell' ou 'keep' com justificativa fundamentada. "
        "Responda APENAS com JSON válido."
    )
)