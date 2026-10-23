"""Application settings, loaded from environment variables / the .env file.

Keeping secrets (DB password, JWT key) in the environment instead of the code
means they never get committed to Git.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Pydantic matches DATABASE_URL in the environment to database_url here and
    # fails at startup if a required value is missing.
    database_url: str
    redis_url: str
    secret_key: str
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    # Razorpay (payments). Empty = payments disabled; the API then answers 503
    # on billing endpoints instead of crashing. Use TEST-mode keys while developing.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    pro_price_paise: int = 19900  # amounts are in paise: 19900 paise = ₹199

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
