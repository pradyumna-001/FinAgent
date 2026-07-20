import logging
import os
from datetime import datetime, timezone, timedelta
import yfinance as yf

from app.core.config import get_llm_client, settings
from app.graph.state import AgentState, QuantOutput
from app.prompts.services.prompt_loader import PromptManagementService
from app.utils.data_preprocessing import DataFlag

logger = logging.getLogger("finagent.agents.quant")

def quant_agent_node(state: AgentState) -> AgentState:
    """
    QuantAgent Node: Computes pure mathematical financial valuation ratios in native Python 
    and uses an LLM exclusively for qualitative commentary.
    """
    run_id = state.get("pipeline_run_id", "UNKNOWN_RUN")
    note_id = state.get("morning_note_id", "UNKNOWN_NOTE")
    ticker = state.get("company_ticker", "UNKNOWN_TICKER")

    logger.info(f"[{run_id}][{note_id}][QuantAgent] Starting quantitative metrics execution for {ticker}.")

    now = datetime.now(timezone.utc)
    last_fetched = state.get("data_freshness", {}).get("company")

    if isinstance(last_fetched, str):
        try:
            last_fetched = datetime.fromisoformat(last_fetched)
        except ValueError:
            logger.warning("Failed to parse ISO string timestamp into datetime format.")
            last_fetched = None
    
    if last_fetched and isinstance(last_fetched, datetime):
        now = datetime.now(timezone.utc)
        age = now - last_fetched
        if age > timedelta(hours=24):
            logger.error(f"[{run_id}][{note_id}][QuantAgent] Data is stale ({age.total_seconds() / 3600:.1f} hours old). Aborting.")
            state["flags"].append(
                DataFlag(
                    source="b3_api",
                    flag_type="high",
                    metadata={"error": "data_outdated"},
                    timestamp=now.isoformat()
                )
            )
            return state

    yf_ticker = ticker if ticker.endswith(".SA") else f"{ticker}.SA"

    try:
        logger.info(f"[{run_id}][{note_id}][QuantAgent] Extracting metrics from yfinance for {yf_ticker}...")
        stock = yf.Ticker(yf_ticker)
        info = stock.info
        
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        eps = info.get("trailingEps")
        enterprise_value = info.get("enterpriseValue")
        ebitda = info.get("ebitda")
        trailing_dy = info.get("dividendYield", 0.0)

        if not current_price:
            raise ValueError(f"Could not retrieve a valid current price for {yf_ticker}")

        pe_ratio = round(current_price / eps, 2) if (eps and eps != 0) else None
        ev_ebitda = round(enterprise_value / ebitda, 2) if (enterprise_value and ebitda and ebitda != 0) else None
        if trailing_dy and trailing_dy > 1.0:
            dividend_yield = round(trailing_dy, 2)
        else:
            dividend_yield = round(trailing_dy * 100, 2) if trailing_dy else 0.0

    except Exception as calc_err:
        fail_msg = f"Deterministic calculation engine failure: {str(calc_err)}"
        logger.error(f"[{run_id}][{note_id}][QuantAgent] {fail_msg}")
        state["flags"].append(
            DataFlag(
                source="quant_agent",
                flag_type="high",
                metadata=fail_msg,
                timestamp=now.isoformat()
            )
        )
        return state

    nvidia_api_key = os.getenv("NVIDIA_API_KEY") or settings.nvidia_api_key
    if not nvidia_api_key:
        logger.warning(f"[{run_id}][{note_id}][QuantAgent] Missing API Key. Storing raw metrics without analysis.")
        state["quant_metrics"] = QuantOutput(
            pe_ratio=pe_ratio,
            ev_ebitda=ev_ebitda,
            dividend_yield=dividend_yield,
            momentum_signal="neutral"
        )
        return state

    try:
        prompt_service = PromptManagementService()
        system_tmpl = prompt_service.load_prompt("quant_agent_system")
        user_tmpl = prompt_service.load_prompt("quant_agent_user")

        formatted_system = system_tmpl.raw_template
        formatted_user = user_tmpl.raw_template.format(
            ticker=ticker,
            pe_ratio=str(pe_ratio or "N/A"),
            ev_ebitda=str(ev_ebitda or "N/A"),
            pb_ratio="N/A",
            dividend_yield=str(dividend_yield),
            ibov_variance_30d="N/A"
        )

        client = get_llm_client()
        target_model = os.getenv("NVIDIA_MODEL", settings.nvidia_model)
        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": formatted_system},
                {"role": "user", "content": formatted_user}
            ],
            temperature=0.1
        )

        raw_signal = response.choices[0].message.content.strip().lower()
        
        momentum_signal = "neutral"
        if "bullish" in raw_signal or "alta" in raw_signal or "compra" in raw_signal:
            momentum_signal = "bullish"
        elif "bearish" in raw_signal or "baixa" in raw_signal or "venda" in raw_signal:
            momentum_signal = "bearish"

        state["quant_metrics"] = QuantOutput(
            pe_ratio=pe_ratio,
            ev_ebitda=ev_ebitda,
            dividend_yield=dividend_yield,
            momentum_signal=momentum_signal
        )
        
        if "data_freshness" not in state:
            state["data_freshness"] = {}
        state["data_freshness"]["quant"] = datetime.now(timezone.utc)
        logger.info(f"[{run_id}][{note_id}][QuantAgent] Successfully completed quantitative processing cycle.")

    except Exception as llm_err:
        logger.error(f"[{run_id}][{note_id}][QuantAgent] Qualitative interpretation failed: {str(llm_err)}")
        state["quant_metrics"] = QuantOutput(
            pe_ratio=pe_ratio,
            ev_ebitda=ev_ebitda,
            dividend_yield=dividend_yield,
            momentum_signal="neutral"
        )

    return state
