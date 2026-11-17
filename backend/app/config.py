from pydantic_settings import BaseSettings


DEFAULT_REPOSITORY_ID = "codebase-ai"


class Settings(BaseSettings):
    gemini_api_key: str = ""
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.7-flash"

    embedding_provider: str = "gemini"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

    database_url: str = (
        "postgresql+psycopg://codebase:codebase@postgres:5432/codebase_ai"
    )

    repository_root: str = "/workspace/repository"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()