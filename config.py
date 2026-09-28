"""
config.py — Central configuration loaded from .env
All parts of the app import from here — never hardcode secrets elsewhere.
"""
import os
from dotenv import load_dotenv

# Load .env from project root (works regardless of where the script is run from)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)


class Config:
    # Database
    DB_HOST     = os.getenv("DB_HOST", "localhost")
    DB_USER     = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME     = os.getenv("DB_NAME", "timetable_db")

    # Nanonets
    NANONETS_API_KEY = os.getenv("NANONETS_API_KEY", "")
    NANONETS_URL     = "https://extraction-api.nanonets.com/api/v1/extract/sync"

    # Flask / JWT
    SECRET_KEY     = os.getenv("SECRET_KEY", "changeme")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "changeme-jwt")
    FLASK_PORT     = int(os.getenv("FLASK_PORT", 5000))
    DEBUG          = os.getenv("FLASK_ENV", "development") == "development"

    # Upload folder
    UPLOAD_FOLDER   = os.path.join(os.path.dirname(__file__), "uploads")
    JSON_OUTPUT     = os.path.join(UPLOAD_FOLDER, "timetable.json")
