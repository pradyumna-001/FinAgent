import os
import logging
from typing import Dict, List
from app.prompts.schemas.prompt_schema import PromptTemplate

logger = logging.getLogger("finagent.prompts.loader")

class PromptManagementService:
    """
    Centralized service responsible for loading, registering and validating
    external prompt template files from the 'app/prompts/' directory
    """
    def __init__(self, prompts_dir: str = None):
        if prompts_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            app_dir = os.path.dirname(current_dir)
            self.prompts_dir = app_dir
        else:
            self.prompts_dir = prompts_dir

        logger.info(f"Initialized PromptManagementService targeting: {self.prompts_dir}")

        self._registry: Dict[str, List[str]] = {
            "macro_agent": ["search_results"],
            "company_agent_system": ["schema_instruction"],
            "company_agent_user": ["ticker", "search_results"],
            "quant_agent_system": [],
            "quant_agent_user": ["ticker", "pe_ratio", "ev_ebitda", "pb_ratio", "dividend_yield", "ibov_variance_30d"],
            "risk_agent_system": ["schema_instruction"],
            "risk_agent_user": ["ticker", "pipeline_context"],
        }

    def load_prompt(self, prompt_name: str) -> PromptTemplate:
        """
        Loads a prompt text file from disk, validates it against the registry 
        and returns a structured PromptTemplate model
        """
        if prompt_name not in self._registry:
            raise ValueError(f"Prompt '{prompt_name}' is not registered in the PromptManagementService")
        
        file_name = f"{prompt_name}.txt"
        file_path = os.path.join(self.prompts_dir, file_name)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_content = f.read()
        except FileNotFoundError as fnf_error:
            logger.error(f"Failed to locate prompt file at {file_path}")
            raise FileNotFoundError(
                f"Prompt file '{file_name}' not found under {self.prompts_dir}"
            ) from fnf_error
        
        required_vars = self._registry[prompt_name]

        for var in required_vars:
            placeholder = f"{{{var}}}"
            if placeholder not in raw_content:
                logger.warning(
                    f"Registered placeholder '{placeholder}' was not found in the raw content of '{file_name}'"
                )

        return PromptTemplate(
            name=prompt_name,
            raw_template=raw_content,
            required_variables=required_vars
        )
