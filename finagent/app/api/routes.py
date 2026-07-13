from fastapi import APIRouter, Depends

from app.schemas.analysis import AnalysisResponse
from app.services.analysis import AnalysisService
from app.api.deps import get_analysis_service

router = APIRouter()

analysis_service = AnalysisService()

@router.get("/")
async def health_check():
    return {
        "status": "ok",
        "service": "FinAgent"
    }

@router.get(
    "/analyze/{ticker}",
    response_model=AnalysisResponse,
)
async def analyze(ticker: str, analysis_service: AnalysisService = Depends(get_analysis_service)) -> AnalysisResponse:
    return analysis_service.analyze(ticker=ticker)