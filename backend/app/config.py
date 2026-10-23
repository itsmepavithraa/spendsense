"""Application settings, loaded from environment variables / the .env file.

Keeping secrets (DB password, JWT key) in the environment instead of the code
means they never get committed to Git.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Pydantic matches DATABASE_URL in the environment to database_url here and
    # fails at startup if a required value is missing.
    database_url: str
    redis_url: str = "redis://localhost:6379/0"  # reserved for multi-server real-time; not used yet
    secret_key: str

    # Browser origins allowed to call the API, comma separated. In production set
    # this to your deployed frontend URL, e.g. https://spendsense.vercel.app
    cors_origins: str = "http://localhost:3000"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    # Razorpay (payments). Empty = payments disabled; the API then answers 503
    # on billing endpoints instead of crashing. Use TEST-mode keys while developing.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    pro_price_paise: int = 19900  # amounts are in paise: 19900 paise = ₹199

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def use_psycopg2_driver(cls, url: str) -> str:
        """Cloud hosts hand out URLs starting with postgres:// or postgresql://,
        but SQLAlchemy needs to be told which driver to use."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg2://" + url[len(prefix):]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
