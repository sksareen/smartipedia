from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://smartipedia:smartipedia@localhost:5434/smartipedia"
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-haiku-4-5-20251001"
    embedding_model: str = "openai/text-embedding-3-small"
    searxng_url: str = "http://localhost:8888"
    umami_website_id: str = ""  # set after creating the site in Umami dashboard
    daily_generation_limit: int = 50  # max new topics generated per day (0 = unlimited)

    # Auth
    session_secret: str = "change-me-in-production"  # signs session cookies
    github_client_id: str = ""
    github_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    base_url: str = "https://smartipedia.com"  # for OAuth redirect URIs

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
