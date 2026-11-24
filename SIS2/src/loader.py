import hashlib
import sqlite3
import sys
from datetime import datetime

import pandas as pd

from src.config import CITIES, CLEANED_CSV, DATA_DIR, DB_PATH

CITY_LIST = ", ".join(f"'{city}'" for city in CITIES)

CREATE_TABLES = f"""
CREATE TABLE IF NOT EXISTS air_quality (
    record_id       TEXT    PRIMARY KEY,
    city            TEXT    NOT NULL CHECK (city IN ({CITY_LIST})),
    latitude        REAL    NOT NULL,
    longitude       REAL    NOT NULL,
    timestamp       TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    hour            INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
    day_of_week     TEXT    NOT NULL,
    is_weekend      INTEGER NOT NULL CHECK (is_weekend IN (0, 1)),
    pm2_5           REAL    NOT NULL CHECK (pm2_5 >= 0),
    pm10            REAL    NOT NULL CHECK (pm10 >= pm2_5),
    us_aqi          INTEGER NOT NULL CHECK (us_aqi BETWEEN 0 AND 500),
    aqi_category    TEXT    NOT NULL,
    pm_ratio        REAL,
    log_pm2_5       REAL,
    pm2_5_zscore    REAL,
    above_who_pm2_5 INTEGER NOT NULL,
    above_who_pm10  INTEGER NOT NULL,
    collected_at    TEXT    NOT NULL,
    UNIQUE (city, timestamp)
);
CREATE TABLE IF NOT EXISTS load_log (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    loaded_at     TEXT    NOT NULL,
    processed     INTEGER NOT NULL,
    inserted      INTEGER NOT NULL,
    skipped       INTEGER NOT NULL,
    rows_in_table INTEGER NOT NULL
);
"""

COLUMNS = ["record_id", "city", "latitude", "longitude", "timestamp", "date", "hour",
           "day_of_week", "is_weekend", "pm2_5", "pm10", "us_aqi", "aqi_category", "pm_ratio",
           "log_pm2_5", "pm2_5_zscore", "above_who_pm2_5", "above_who_pm10", "collected_at"]

INSERT = (f"INSERT INTO air_quality ({', '.join(COLUMNS)}) "
          f"VALUES ({', '.join('?' for _ in COLUMNS)}) ON CONFLICT DO NOTHING")

VERIFY_QUERIES = {
    "Total rows": "SELECT COUNT(*) AS total_rows FROM air_quality",
    "Distinct record_id": "SELECT COUNT(DISTINCT record_id) AS distinct_ids FROM air_quality",
    "Duplicate city+hour (must be empty)": """
        SELECT city, timestamp, COUNT(*) AS copies FROM air_quality
        GROUP BY city, timestamp HAVING COUNT(*) > 1""",
    "Rows with missing values (must be 0)": """
        SELECT COUNT(*) AS rows_with_nulls FROM air_quality
        WHERE pm2_5 IS NULL OR pm10 IS NULL OR us_aqi IS NULL OR timestamp IS NULL""",
    "Rows per city and period": """
        SELECT city, COUNT(*) AS rows, MIN(timestamp) AS first_hour, MAX(timestamp) AS last_hour
        FROM air_quality GROUP BY city ORDER BY city""",
    "Average pollution per city": """
        SELECT city, ROUND(AVG(pm2_5), 2) AS avg_pm2_5, ROUND(AVG(pm10), 2) AS avg_pm10,
               ROUND(AVG(us_aqi), 1) AS avg_aqi, SUM(above_who_pm2_5) AS hours_above_who
        FROM air_quality GROUP BY city ORDER BY avg_pm2_5 DESC""",
    "Top 5 most polluted hours": """
        SELECT city, timestamp, pm2_5, us_aqi, aqi_category FROM air_quality
        ORDER BY pm2_5 DESC LIMIT 5""",
    "Load history": "SELECT * FROM load_log ORDER BY run_id",
}


def connect():
    DATA_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(CREATE_TABLES)
    return connection


def to_rows(df):
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M")
    df["collected_at"] = pd.to_datetime(df["collected_at"]).dt.strftime("%Y-%m-%dT%H:%M:%S")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["city"] = df["city"].astype(str)
    for column in ["is_weekend", "above_who_pm2_5", "above_who_pm10"]:
        df[column] = df[column].map({True: 1, False: 0, "True": 1, "False": 0}).astype(int)
    df["hour"] = df["hour"].astype(int)
    df["us_aqi"] = df["us_aqi"].astype(int)
    df = df[COLUMNS].astype(object).where(df[COLUMNS].notna(), None)
    return list(df.itertuples(index=False, name=None))


def table_fingerprint(connection):
    rows = connection.execute("SELECT * FROM air_quality ORDER BY record_id").fetchall()
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]


def count_rows(connection):
    return connection.execute("SELECT COUNT(*) FROM air_quality").fetchone()[0]


def load(df, connection):
    rows = to_rows(df)
    before = count_rows(connection)
    try:
        with connection:
            connection.executemany(INSERT, rows)
            after = count_rows(connection)
            inserted = after - before
            connection.execute(
                "INSERT INTO load_log (loaded_at, processed, inserted, skipped, rows_in_table) "
                "VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), len(rows), inserted,
                 len(rows) - inserted, after))
    except sqlite3.Error as error:
        sys.exit(f"Database error while loading: {error}")
    print(f"Processed: {len(rows)}, inserted: {inserted}, skipped as duplicates: "
          f"{len(rows) - inserted}, rows in table: {after}")
    return {"processed": len(rows), "inserted": inserted, "rows_in_table": after}


def verify(connection):
    print("\nSQL verification:")
    for title, query in VERIFY_QUERIES.items():
        result = pd.read_sql_query(query, connection)
        print(f"\n-- {title}")
        print("(no rows)" if result.empty else result.to_string(index=False))


def run(cleaned_df=None, times=2):
    if cleaned_df is None:
        if not CLEANED_CSV.exists():
            sys.exit(f"{CLEANED_CSV.name} not found. Run the cleaner first: python -m src.cleaner")
        cleaned_df = pd.read_csv(CLEANED_CSV)
    connection = connect()
    results = []
    for attempt in range(1, times + 1):
        print(f"\nLoad run {attempt}:")
        results.append(load(cleaned_df, connection))
        results[-1]["fingerprint"] = table_fingerprint(connection)
        print(f"Table fingerprint: {results[-1]['fingerprint']}")
    if times > 1:
        unchanged = len({r["fingerprint"] for r in results[1:]}) == 1 and results[-1]["inserted"] == 0
        same_as_first = results[0]["fingerprint"] == results[-1]["fingerprint"]
        print(f"\nIdempotency check: repeated load inserted {results[-1]['inserted']} rows, "
              f"table content unchanged: {same_as_first} -> {'PASSED' if unchanged and same_as_first else 'FAILED'}")
    stored = count_rows(connection)
    print(f"Processed records: {len(cleaned_df)}, stored in SQLite: {stored}")
    verify(connection)
    connection.close()
    return stored


if __name__ == "__main__":
    run(times=1 if "--once" in sys.argv else 2)
