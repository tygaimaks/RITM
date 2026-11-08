"""Константы и настройки бота."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DB_FILE: str = os.getenv("DB_FILE", "rhythm.db")
MAIN_ADMIN_ID: str = os.getenv("MAIN_ADMIN_ID", "")
TIMEZONE: str = os.getenv("TIMEZONE", "")
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")
GIGACHAT_CLIENT_ID: str = os.getenv("GIGACHAT_CLIENT_ID", "")
GIGACHAT_CLIENT_SECRET: str = os.getenv("GIGACHAT_CLIENT_SECRET", "")