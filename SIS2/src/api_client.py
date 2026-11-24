import json
import time
from datetime import datetime

import pandas as pd
import requests

from src.config import API_URL, CITIES, DATA_DIR, RAW_CSV, RAW_JSON


def fetch_city(city, lat, lon, retries=3):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5,pm10,us_aqi",
        "past_days": 7,
        "forecast_days": 0,
        "timezone": "Asia/Almaty",
    }
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(API_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            if "hourly" not in data:
                raise ValueError("no hourly data in response")
            return data
        except (requests.RequestException, ValueError) as error:
            print(f"{city}: attempt {attempt} failed - {error}")
            time.sleep(2)
    return None


def to_records(city, data, collected_at):
    hourly = data["hourly"]
    records = []
    for i, timestamp in enumerate(hourly["time"]):
        records.append({
            "record_id": f"{city}_{timestamp}",
            "city": city,
            "latitude": data["latitude"],
            "longitude": data["longitude"],
            "timestamp": timestamp,
            "pm2_5": hourly["pm2_5"][i],
            "pm10": hourly["pm10"][i],
            "us_aqi": hourly["us_aqi"][i],
            "collected_at": collected_at,
        })
    return records


def collect_all():
    collected_at = datetime.now().isoformat(timespec="seconds")
    records = []
    for city, (lat, lon) in CITIES.items():
        data = fetch_city(city, lat, lon)
        if data is None:
            print(f"{city}: skipped")
            continue
        city_records = to_records(city, data, collected_at)
        records.extend(city_records)
        print(f"{city}: {len(city_records)} records")
    print(f"Total collected: {len(records)}")
    return records


def save_raw(records):
    DATA_DIR.mkdir(exist_ok=True)
    pd.DataFrame(records).to_csv(RAW_CSV, index=False)
    with open(RAW_JSON, "w") as file:
        json.dump(records, file, indent=1)
    print(f"Saved raw data to {RAW_CSV.name} and {RAW_JSON.name}")


def load_raw():
    with open(RAW_JSON) as file:
        return json.load(file)


if __name__ == "__main__":
    data = collect_all()
    if data:
        save_raw(data)
