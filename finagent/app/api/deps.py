from fastapi import Depends
from app.services.analysis import AnalysisService

def get_analysis_service() -> AnalysisService:
    return AnalysisService(
        openai_client=None,
        market_data_client=None,
        news_client=None,
        db_session=None
    )
