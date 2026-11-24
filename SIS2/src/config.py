import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_CSV = DATA_DIR / "raw_data.csv"
RAW_JSON = DATA_DIR / "raw_data.json"
CONSUMED_CSV = DATA_DIR / "consumed_data.csv"

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
