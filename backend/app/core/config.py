from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "PlagiaScan"
    API_V1_STR: str = "/api/v1"
    
    # --- Fluxbase Database (primary) ---
    FLUXBASE_URL: str = "https://fluxbase.vercel.app/api/execute-sql"
    FLUXBASE_API_KEY: Optional[str] = None
    FLUXBASE_PROJECT_ID: Optional[str] = None

    # --- SQLite fallback (used if Fluxbase credentials not set) ---
    DATABASE_URL: str = "sqlite:///./plagiascan.db"
    
    REDIS_URL: str = "redis://localhost:6379/0" 
    
    # Qdrant Vector DB
    QDRANT_URL: str = "local"
    QDRANT_API_KEY: Optional[str] = None
    
    SECRET_KEY: str = "supersecretkey"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Email (for notifications) ---
    EMAIL_ADDRESS: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USE_SSL: bool = False

    # --- Web Search Providers (Optional) ---
    BRAVE_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    # --- Detection Pipeline Settings ---
    DEFAULT_NGRAM_SIZE: int = 25
    MAX_URLS_PER_SCAN: int = 30
    PAGE_FETCH_TIMEOUT: float = 9.0
    PAGE_CACHE_TTL_SECONDS: int = 3600

    _fluxbase_active: Optional[bool] = None

    @property
    def use_fluxbase(self) -> bool:
        """True if Fluxbase credentials are configured and Fluxbase is active."""
        if self._fluxbase_active is False:
            return False
        return bool(self.FLUXBASE_API_KEY and self.FLUXBASE_PROJECT_ID and
                    "YOUR_API_KEY" not in (self.FLUXBASE_API_KEY or ""))

    def disable_fluxbase(self):
        self._fluxbase_active = False

    def enable_fluxbase(self):
        self._fluxbase_active = True

    class Config:
        env_file = ".env"

settings = Settings()
