from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://smartipedia:smartipedia@localhost:5434/smartipedia"
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-4"
    embedding_model: str = "openai/text-embedding-3-small"
    searxng_url: str = "http://localhost:8888"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
