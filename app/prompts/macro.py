from dataclasses import dataclass


@dataclass(frozen=True)
class MacroPrompts:
    system: str

    def build_user_prompt(self, raw_text: str) -> str:
        return (
            "Summarize the following macro news into a concise paragraph: \n\n" + 
            raw_text
        )


MACRO_PROMPTS = MacroPrompts(
    system=(
        "You are a macroeconomic analyst covering the Brazilian market. "
        "Summarize the most relevant macro news into a concise context. "
        "Focus on: interest rates (Selic), inflation (IPCA), GDP, "
        "FX (BRL/USD), and fiscal policy. Respond in Portuguese."
    ),
)