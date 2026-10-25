import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "coffee-estate-dev-secret-key-change-in-prod")
    
    # Database config: defaults to SQLite for immediate dev/test, supports MySQL via DATABASE_URL
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'estate.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    } if "mysql" in os.getenv("DATABASE_URL", "") else {}

    # Session & Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours

    # Rate Limiting
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "200 per day;50 per hour")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_STRATEGY = "fixed-window"

    # Theme Brand Palette
    THEME_COLORS = {
        "forest_green": "#234735",
        "leaf_green": "#5F8663",
        "warm_cream": "#F6F3E9",
        "coffee_brown": "#7A4D2B",
    }

    # Uploads
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
