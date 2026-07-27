from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL / TimescaleDB
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "nba_props_db"
    POSTGRES_USER: str = "quant_user"
    POSTGRES_PASSWORD: str = "quant_password"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # API Keys & League Configuration
    LEAGUE: str = "nba"  # "nba" or "wnba"
    THE_ODDS_API_KEY: str = ""
    SPORTRADAR_API_KEY: str = ""

    # Risk & Trading Parameters
    MIN_EV_THRESHOLD: float = 0.03
    MIN_EDGE_OVER_CONSENSUS: float = 0.015
    KELLY_FRACTION: float = 0.125
    MAX_WAGER_CAP: float = 500.00
    BANKROLL_AMOUNT: float = 10000.00

    # Webhook Alerting
    WEBHOOK_URL: str = ""


settings = Settings()
