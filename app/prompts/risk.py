from dataclasses import dataclass

from app.graph.state import MacroOutput, CompanyEvent, QuantOutput
from app.utils.flags import DataFlag


@dataclass(frozen=True)
class RiskPrompts:
    system: str

    def build_user_prompt(
            self,
            *,
            macro_context: MacroOutput | None,
            company_events: list[CompanyEvent],
            quant_metrics: QuantOutput | None,
            data_flags: list[DataFlag],
    ) -> str:
        lines: list[str] = []
        lines.append("## Macro context")
        lines.append(str(macro_context))
        lines.append("\n## Company events")
        for ev in company_events:
            lines.append(f"- {ev.get('title', '')}: {ev.get('summary', '')}")
        lines.append("\n## Quant metrics")
        lines.append(str(quant_metrics))
        if data_flags:
            lines.append("\n## Known data gaps (DataFlags)")
            for f in data_flags:
                lines.append(f"- [{f.severity.value}] {f.source}: {f.message}")
        lines.append(
            "\n\nList the risks. Answer ONLY with valid JSON: a list of "
            "objects with keys probability (float 0-1), impact "
            "('low' | 'medium' | 'high'), description (str), severity "
            "('info' | 'warning' | 'fatal')."
        )
        return "\n".join(lines)


RISK_PROMPTS = RiskPrompts(
    system=(
        "You are a skeptical risk analyst on a Brazilian investment "
        "team. Your job is to surface inconsistencies, ignored risks, "
        "and biases in what the macro, company, and quant agents "
        "produced. You do NOT fetch external data - you only analyze "
        "what the other agents produced. If there are data gaps "
        "(DataFlags), name them as additional risk. Respond ONLY "
        "with valid JSON: a list of objects."
    ),
)
