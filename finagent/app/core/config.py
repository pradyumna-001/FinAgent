from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "FinAgent"
    enviroment: str = "development"

settings = Settings()
