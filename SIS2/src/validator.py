import sys

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from src.config import CITIES, CONSUMED_CSV, DATA_DIR, INVALID_CSV, VALID_CSV

LAT_RANGE = (40.5, 55.5)
LON_RANGE = (46.5, 87.5)
EARLIEST_TIMESTAMP = pd.Timestamp("2013-01-01")
FUTURE_TOLERANCE = pd.Timedelta(days=1)
ID_PATTERN = r"^[A-Za-z]+_\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"


def _as_number(series):
    return pd.to_numeric(series, errors="coerce")


def _as_time(series):
    return pd.to_datetime(series, errors="coerce")


def pm10_not_below_pm25(df):
    pm25, pm10 = _as_number(df["pm2_5"]), _as_number(df["pm10"])
    return pm25.isna() | pm10.isna() | (pm10 >= pm25)


def timestamp_not_in_future(df):
    timestamp, collected = _as_time(df["timestamp"]), _as_time(df["collected_at"])
    return timestamp.isna() | collected.isna() | (timestamp <= collected + FUTURE_TOLERANCE)


def _normalized(series):
    return series.astype(str).str.strip().str.title()


def record_id_matches_city_and_time(df):
    timestamp = _as_time(df["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M")
    return df["record_id"].astype(str).str.strip() == _normalized(df["city"]) + "_" + timestamp


schema = pa.DataFrameSchema(
    columns={
        "record_id": pa.Column(str, nullable=False, checks=pa.Check.str_matches(ID_PATTERN)),
        "city": pa.Column(str, nullable=False, checks=pa.Check(
            lambda s: _normalized(s).isin(list(CITIES)), name=f"city_in_{list(CITIES)}")),
        "latitude": pa.Column(float, pa.Check.in_range(*LAT_RANGE), coerce=True, nullable=False),
        "longitude": pa.Column(float, pa.Check.in_range(*LON_RANGE), coerce=True, nullable=False),
        "timestamp": pa.Column(
            pa.DateTime,
            pa.Check(lambda s: _as_time(s).isna() | (_as_time(s) >= EARLIEST_TIMESTAMP),
                     name=f"not_before_{EARLIEST_TIMESTAMP.date()}"),
            coerce=True,
            nullable=False,
        ),
        "collected_at": pa.Column(pa.DateTime, coerce=True, nullable=False),
        "pm2_5": pa.Column(float, pa.Check.in_range(0, 1000), coerce=True, nullable=True),
        "pm10": pa.Column(float, pa.Check.in_range(0, 2000), coerce=True, nullable=True),
        "us_aqi": pa.Column(
            float,
            [
                pa.Check.in_range(0, 500),
                pa.Check(lambda s: s % 1 == 0, element_wise=False, name="is_whole_number"),
            ],
            coerce=True,
            nullable=True,
        ),
    },
    checks=[
        pa.Check(pm10_not_below_pm25, name="pm10_not_below_pm2_5"),
        pa.Check(timestamp_not_in_future, name="timestamp_not_in_future"),
        pa.Check(record_id_matches_city_and_time, name="record_id_matches_city_and_time"),
    ],
    strict=False,
    name="air_quality_schema",
)

RULES = [
    "record_id is required and has the format City_YYYY-MM-DDTHH:MM",
    f"city is one of: {', '.join(CITIES)} (case and extra spaces are ignored)",
    f"latitude in {LAT_RANGE}, longitude in {LON_RANGE} (inside Kazakhstan)",
    f"timestamp and collected_at are valid date/times, timestamp >= {EARLIEST_TIMESTAMP.date()}",
    "pm2_5 in [0, 1000] and pm10 in [0, 2000] μg/m³ (missing allowed)",
    "us_aqi is a whole number in [0, 500] (missing allowed)",
    "pm10 >= pm2_5 (PM10 contains PM2.5)",
    "timestamp is not after collected_at (+1 day time-zone tolerance)",
    "record_id equals city + '_' + timestamp",
]


def make_test_records():
    base = {"latitude": 43.2, "longitude": 76.9, "collected_at": "2026-11-24T12:00:00", "is_test": True}
    return [
        {**base, "record_id": "Almaty_2026-11-17T00:30", "city": "Almaty",
         "timestamp": "2026-11-17T00:30", "pm2_5": -5.0, "pm10": 12.0, "us_aqi": 650},
        {**base, "record_id": "Paris_2026-11-17T01:30", "city": "Paris", "latitude": 48.86,
         "longitude": 2.35, "timestamp": "2026-11-17T01:30", "pm2_5": 10.0, "pm10": 15.0, "us_aqi": 40},
        {**base, "record_id": "Astana_not-a-date", "city": "Astana", "latitude": 51.2, "longitude": 71.4,
         "timestamp": "not-a-date", "pm2_5": 10.0, "pm10": 15.0, "us_aqi": 40},
        {**base, "record_id": "Shymkent_2031-01-01T00:00", "city": "Shymkent", "latitude": 42.3,
         "longitude": 69.6, "timestamp": "2031-01-01T00:00", "pm2_5": 80.0, "pm10": 40.0, "us_aqi": 55.5},
        {**base, "record_id": None, "city": "Atyrau", "latitude": 47.1, "longitude": 51.9,
         "timestamp": "2026-11-17T02:00", "pm2_5": 10.0, "pm10": 15.0, "us_aqi": 40},
    ]


def collect_errors(failure_cases):
    errors, global_errors = {}, []
    for case in failure_cases.itertuples():
        if case.schema_context == "DataFrameSchema":
            message = f"row: {case.check}"
        elif str(case.check).startswith("dtype("):
            continue
        else:
            message = f"{case.column}: {case.check} (value: {case.failure_case})"
        if pd.isna(case.index):
            global_errors.append(message)
        else:
            errors.setdefault(int(case.index), []).append(message)
    return errors, global_errors


def validate(df, add_test_records=True):
    df = df.copy().reset_index(drop=True)
    if "is_test" not in df.columns:
        df["is_test"] = False
    if add_test_records:
        df = pd.concat([df, pd.DataFrame(make_test_records())], ignore_index=True)
    df["is_test"] = df["is_test"].fillna(False).astype(bool)

    print("Validation rules:")
    for number, rule in enumerate(RULES, 1):
        print(f"  {number}. {rule}")

    try:
        schema.validate(df, lazy=True)
        errors, global_errors = {}, []
    except SchemaErrors as error:
        errors, global_errors = collect_errors(error.failure_cases)
    for message in global_errors:
        print(f"Schema-level error: {message}")

    invalid_mask = df.index.isin(list(errors))
    invalid = df[invalid_mask].copy()
    invalid["errors"] = [" | ".join(dict.fromkeys(errors[i])) for i in invalid.index]

    valid = df[~invalid_mask & ~df["is_test"]].drop(columns="is_test")
    valid = schema.validate(valid)

    real_total = int((~df["is_test"]).sum())
    real_invalid = int((~invalid["is_test"]).sum())
    test_caught = int(invalid["is_test"].sum())
    test_total = int(df["is_test"].sum())
    print(f"\nChecked: {len(df)} records ({real_total} from Kafka + {test_total} test records)")
    print(f"Valid: {len(valid)}, invalid: {len(invalid)} "
          f"(real: {real_invalid}, test records caught: {test_caught}/{test_total})")
    if len(invalid):
        print("\nInvalid records:")
        for row in invalid.itertuples():
            label = "TEST" if row.is_test else "REAL"
            print(f"  [{label}] {row.record_id}: {row.errors}")
    return valid, invalid


def save(valid, invalid):
    DATA_DIR.mkdir(exist_ok=True)
    valid.to_csv(VALID_CSV, index=False)
    invalid.to_csv(INVALID_CSV, index=False)
    print(f"Saved {VALID_CSV.name} ({len(valid)}) and {INVALID_CSV.name} ({len(invalid)})")


def run(records=None):
    if records is None:
        if not CONSUMED_CSV.exists():
            sys.exit(f"{CONSUMED_CSV.name} not found. Run the consumer first: python -m src.consumer")
        df = pd.read_csv(CONSUMED_CSV)
    else:
        df = pd.DataFrame(records)
    valid, invalid = validate(df)
    save(valid, invalid)
    return valid, invalid


if __name__ == "__main__":
    run()
