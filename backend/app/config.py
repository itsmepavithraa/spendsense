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

    # ---- running as a public service ---------------------------------------------
    # Switch sign-ups off instantly (for example if the site is being abused).
    allow_registration: bool = True
    # Stop accepting sign-ups beyond this many accounts, to protect a small free database.
    # 0 means no limit.
    max_users: int = 0
    # Each account may store at most this many transactions (stops one user filling the database).
    max_transactions_per_user: int = 50_000
    # Behind a hosting proxy (Render, Vercel) the real visitor address arrives in the
    # X-Forwarded-For header. Turn this on ONLY when such a proxy sits in front of the API,
    # otherwise anyone could fake their address and dodge the rate limits.
    trust_proxy: bool = False
    rate_limit_enabled: bool = True
    password_blocklist_enabled: bool = True  # refuse the most common passwords at sign-up
    # The public demo login. It is allowed to use demo-only tools such as the bank-feed simulator.
    demo_email: str = "demo@spendsense.com"

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
    def payments_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
