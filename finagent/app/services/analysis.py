from app.schemas.analysis import AnalysisResponse

class AnalysisService:
    def __init__(
            self,
            openai_client = None,
            market_data_client = None,
            news_client = None,
            db_session = None,
    ):
        self.openai_client = openai_client
        self.market_data_client = market_data_client
        self.news_client = news_client
        self.db_session = db_session

    def analyze(self, ticker: str) -> AnalysisResponse:
        return AnalysisResponse(
            ticker=ticker,
            message=f"Skeleton analysis for {ticker} initiated succcessfully.",
        )
