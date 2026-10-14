"""All settings come from environment variables, so the same code runs locally and in production."""
import os
import secrets

try:  # local development: read .env if python-dotenv is installed (it isn't needed in production)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./invisible_cloud.db")
    # Hosting providers often hand out postgres:// URLs; SQLAlchemy wants an explicit driver.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings:
    app_name = os.getenv("APP_NAME", "Invisible Cloud")
    # Signs the workspace cookie. Must be set in production so cookies survive restarts.
    secret_key = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
    cookie_secure = _bool("COOKIE_SECURE", False)
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model = os.getenv("AI_MODEL", "claude-sonnet-5-5")
    ai_limit_per_workspace_per_hour = _int("AI_LIMIT_PER_WORKSPACE_PER_HOUR", 40)
    ai_limit_per_day = _int("AI_LIMIT_PER_DAY", 1000)
    workspace_ttl_days = _int("WORKSPACE_TTL_DAYS", 7)
    max_upload_mb = _int("MAX_UPLOAD_MB", 5)


settings = Settings()
