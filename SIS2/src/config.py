import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
FIGURES_DIR = PROJECT_DIR / "figures"
DOCS_DIR = PROJECT_DIR / "docs"
RAW_CSV = DATA_DIR / "raw_data.csv"
RAW_JSON = DATA_DIR / "raw_data.json"
CONSUMED_CSV = DATA_DIR / "consumed_data.csv"
VALID_CSV = DATA_DIR / "validated_data.csv"
INVALID_CSV = DATA_DIR / "invalid_records.csv"
CLEANED_CSV = DATA_DIR / "cleaned_data.csv"
CITY_SUMMARY_CSV = DATA_DIR / "city_summary.csv"
HOURLY_PIVOT_CSV = DATA_DIR / "city_hour_pivot.csv"
DB_PATH = DATA_DIR / "output.db"
EDA_RESULTS_MD = DOCS_DIR / "eda_results.md"

WHO_PM25_24H = 15.0
WHO_PM10_24H = 45.0

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
CITIES = {
    "Almaty": (43.2389, 76.8897),
    "Astana": (51.1694, 71.4491),
    "Shymkent": (42.3417, 69.5901),
    "Atyrau": (47.1167, 51.8833),
    "Karaganda": (49.8047, 73.1094),
}

KAFKA_SERVER = os.getenv("KAFKA_SERVER", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "kz_air_quality")
KAFKA_GROUP = os.getenv("KAFKA_GROUP", "air-quality-consumer")
