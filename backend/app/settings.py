from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/job_assistant"
    )
    jwt_secret: str = "change-me"
    jwt_exp_minutes: int = 1440
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_project: Optional[str] = None
    openai_org: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
