from sqlalchemy import select, text

from app.db.models import Company, PortfolioHolding
from app.db.session import SessionLocal


async def get_portfolio_tickers(portfolio_id: int, manager_id: int) -> list[str]:
    """Fetch all unique ticker symbols for a portfolio.

    Joins PortfolioHolding with Company to get tickers, applies RLS via
    SET LOCAL app.manager_id, and deduplicates results while preserving order.

    Args:
        portfolio_id: The portfolio to fetch holdings for.
        manager_id: The manager owning the portfolio, used for RLS.

    Returns:
        A list of unique ticker symbols for the portfolio.
        Empty list if portfolio has no holdings or does not exist.
     """

    async with SessionLocal() as session:
        await session.execute(text(f"SET LOCAL app.manager_id = {manager_id}"))

        stmt = select(Company.ticker).join(
            PortfolioHolding, PortfolioHolding.company_id == Company.id
        ).where(PortfolioHolding.portfolio_id == portfolio_id)

        result = await session.execute(stmt)
        tickers = result.scalars().all()

        return list(dict.fromkeys(tickers))  # Deduplicate while preserving order
