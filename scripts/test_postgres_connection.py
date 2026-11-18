"""Explicit environment-configured connectivity check; no import-time IO."""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv


def main():
    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL before running the connection check.")
    try:
        with create_engine(url).connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Database connection successful")
    except Exception:
        raise SystemExit("Database connection failed; check your local configuration.") from None


if __name__ == "__main__":
    main()
