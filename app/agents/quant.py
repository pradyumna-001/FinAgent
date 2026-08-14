from datetime import datetime, UTC
import logging

from app.graph.state import AgentState, QuantOutput
from app.services.yfinance import YfinanceService, YfinanceError
from app.utils.flags import DataFlag, Severity


logger = logging.getLogger(__name__)


async def quant_agent_node(state: AgentState) -> AgentState:
    """Pull financial metrics via YfinanceService, build a QuantOutput, and update
    AgentState in-place. Failures append a DataFlag and return with quant_metrics=None -
    never raises.
    """
    logger.info(
        "quant_agent_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"],
        },
    )

    try:
        yfinance_service = YfinanceService(ticker=state["company_ticker"])
    except YfinanceError as exc:
        state["flags"].append(
            DataFlag(source="yfinance", severity=Severity.FATAL, message=str(exc))
        )
        state["quant_metrics"] = None
        state["data_freshness"]["quant"] = datetime.now(UTC)
        return state

    result = await yfinance_service.search()
    if result.error:
        state["flags"].append(result.error)
        state["quant_metrics"] = None
        state["data_freshness"]["quant"] = datetime.now(UTC)
        return state

    assert result.metrics is not None

    quant_metrics: QuantOutput = {
        "pl": result.metrics.pl,
        "ev_ebitda": result.metrics.ev_ebitda,
        "p_vpa": result.metrics.p_vpa,
        "dividend_yield": result.metrics.dividend_yield,
        "dev_ibov": result.metrics.dev_ibov,
        "fetched_at": result.metrics.fetched_at,
        "market_time": result.metrics.market_time,
    }

    state["quant_metrics"] = quant_metrics
    state["data_freshness"]["quant"] = (
        result.metrics.market_time
        if result.metrics.market_time is not None
        else datetime.now(UTC)
    )
    return state
