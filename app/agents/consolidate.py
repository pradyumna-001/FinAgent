import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import Company
from app.db.session import SessionLocal
from app.graph.state import AgentState
from app.utils.flags import DataFlag, Severity

logger = logging.getLogger(__name__)


async def consolidate_node(state: AgentState) -> dict:
    """Consolidate per-ticker data into portfolio-level fields.

    Runs once after parallel per-ticker agents complete.
    Computes sector weights, concentration risk flags, and data quality flags.
    """
    logger.info(
        "consolidate_node_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"]
        }
    )

    tickers = state.get("company_tickers", [])
    if not tickers:
        return {
            "sector_weights": {},
            "portfolio_risk_flags": [],
            "portfolio_data_flags": [],
            "data_freshness": {"portfolio": datetime.now(UTC)},
            "flags": []
        }

    # Fetch sectors for all tickers
    async with SessionLocal() as session:
        result = await session.execute(
            select(Company.ticker, Company.sector)
            .where(Company.ticker.in_(tickers))
        )
        sectors = {row[0]: row[1] or "Unknown" for row in result}

    # Compute sector weights (equal weight for now)
    sector_weights: dict[str, float] = {}
    for t in tickers:
        sector = sectors.get(t, "Unknown")
        sector_weights[sector] = sector_weights.get(sector, 0) + 1 / len(tickers)

    # Portfolio risk flags (concentration > 40%)
    portfolio_risk_flags = []
    for sector, weight in sector_weights.items():
        if weight > 0.4:
            portfolio_risk_flags.append({
                "probability": 0.8,
                "impact": "high",
                "description": f"Sector concentration: {sector} = {weight:.0%}",
                "severity": "WARNING"
            })

    # Portfolio data flags (stale tickers)
    stale_count = sum(
        1 for t in tickers
        if state["data_freshness"].get(t)
        and (datetime.now(UTC) - state["data_freshness"][t]).total_seconds() > 86400
    )
    portfolio_data_flags = []
    if stale_count > 0:
        portfolio_data_flags.append(DataFlag(
            source="consolidate",
            severity=Severity.WARNING,
            message=f"{stale_count}/{len(tickers)} tickers have stale data (>24h)"
        ))

    return {
        "sector_weights": sector_weights,
        "portfolio_risk_flags": portfolio_risk_flags,
        "portfolio_data_flags": portfolio_data_flags,
        "data_freshness": {"portfolio": datetime.now(UTC)},
        "flags": []
    }
