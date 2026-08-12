from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyPrompts:
    system: str

    def build_user_prompt(self, raw_text: str) -> str:
        """Build the user-message text sent to the LLM.

        Args:
            raw_text: Non-empty string with the article title, content,
                and source URL concatenated by the CompanyAgent.

        Returns:
            A formatted Portuguese instruction prompt embedding raw_text.

        Raises:
            ValueError: if raw_text is empty.
        """
        if not raw_text:
            raise ValueError("raw_text must be non-empty")
        return (
            "Extract and summarize recent company events from the following "
            "news into a concise Portuguese summary (3-5 sentences). Focus "
            "on: earnings, regulatory filings (CVM), management changes, "
            "M&A, and material fact announcements.\n\n"
            f"{raw_text}"
        )


COMPANY_PROMPTS = CompanyPrompts(
    system=(
        "You are a Brazilian financial news analyst covering B3 companies. "
        "Extract the most relevant recent events for the company and "
        "summarize them concisely in Portuguese. Focus on: earnings "
        "releases, CVM filings, management changes, M&A, and material "
        "fact announcements."
    ),
)
