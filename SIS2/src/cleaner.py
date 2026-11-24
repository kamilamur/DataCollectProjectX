import sys

import numpy as np
import pandas as pd

from src.config import (CITIES, CITY_SUMMARY_CSV, CLEANED_CSV, DATA_DIR, HOURLY_PIVOT_CSV,
                        VALID_CSV, WHO_PM10_24H, WHO_PM25_24H)

MEASUREMENTS = ["pm2_5", "pm10", "us_aqi"]
MAX_INTERPOLATION_GAP = 3

AQI_BINS = [0, 50, 100, 150, 200, 300, 500]
AQI_LABELS = ["Good", "Moderate", "Unhealthy for sensitive groups", "Unhealthy",
              "Very unhealthy", "Hazardous"]


def standardize_text(df):
    df["city"] = df["city"].astype(str).str.strip().str.title()
    df["record_id"] = df["record_id"].astype(str).str.strip()
    return df


def convert_types(df):
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce")
    for column in ["latitude", "longitude", "pm2_5", "pm10", "us_aqi"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["city"] = pd.Categorical(df["city"], categories=list(CITIES))
    return df


def remove_duplicates(df):
    before = len(df)
    exact = int(df.duplicated().sum())
    df = df.drop_duplicates()
    same_id = int(df.duplicated(subset="record_id").sum())
    df = (df.sort_values("collected_at")
            .drop_duplicates(subset="record_id", keep="last")
            .sort_values(["city", "timestamp"])
            .reset_index(drop=True))
    print(f"Duplicates: {exact} exact, {same_id} with the same record_id -> "
          f"removed {before - len(df)}")
    return df


def fill_short_gaps(series):
    is_missing = series.isna()
    gap_id = (~is_missing).cumsum()
    gap_length = is_missing.groupby(gap_id).transform("sum")
    interpolated = series.interpolate(limit_area="inside")
    return series.where(~(is_missing & (gap_length <= MAX_INTERPOLATION_GAP)), interpolated)


def handle_missing(df):
    missing = df[MEASUREMENTS].isna().sum()
    print("Missing values before cleaning:")
    for column, count in missing.items():
        print(f"  {column}: {count} ({count / len(df):.1%})")
    if missing.sum():
        df[MEASUREMENTS] = (df.groupby("city", observed=True)[MEASUREMENTS]
                              .transform(fill_short_gaps))
    filled = int(missing.sum() - df[MEASUREMENTS].isna().sum().sum())
    before = len(df)
    df = df.dropna(subset=MEASUREMENTS).reset_index(drop=True)
    print(f"Interpolated cells: {filled}, rows dropped (gaps > {MAX_INTERPOLATION_GAP} h "
          f"or at the edges): {before - len(df)}")
    df["us_aqi"] = np.rint(df["us_aqi"]).astype(int)
    return df


def add_features(df):
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.day_name()
    df["is_weekend"] = df["timestamp"].dt.dayofweek >= 5

    df["pm_ratio"] = np.where(df["pm10"] > 0, np.round(df["pm2_5"] / df["pm10"], 3), np.nan)
    df["log_pm2_5"] = np.round(np.log1p(df["pm2_5"]), 4)
    city_mean = df.groupby("city", observed=True)["pm2_5"].transform("mean")
    city_std = df.groupby("city", observed=True)["pm2_5"].transform("std")
    df["pm2_5_zscore"] = np.round((df["pm2_5"] - city_mean) / np.where(city_std > 0, city_std, 1), 3)
    df["above_who_pm2_5"] = df["pm2_5"].to_numpy() > WHO_PM25_24H
    df["above_who_pm10"] = df["pm10"].to_numpy() > WHO_PM10_24H
    category_index = np.digitize(df["us_aqi"], AQI_BINS[1:-1], right=True)
    df["aqi_category"] = np.array(AQI_LABELS)[category_index]
    return df


def show_filtering(df):
    evening_peaks = df[(df["pm2_5"] > 35) & (df["hour"].between(18, 23)) & (~df["is_weekend"])]
    print(f"Filter - weekday evening hours (18-23) with PM2.5 > 35: {len(evening_peaks)} records")
    print(evening_peaks["city"].value_counts().to_string())
    outliers = df[(df["pm2_5_zscore"].abs() > 3) | (df["pm10"] > 3 * df["pm10"].median())]
    print(f"Filter - unusual values (|z| > 3 or PM10 > 3x median): {len(outliers)} records")
    return evening_peaks


def summarize(df):
    city_summary = (df.groupby("city", observed=True)
                      .agg(records=("record_id", "count"),
                           pm2_5_mean=("pm2_5", "mean"),
                           pm2_5_median=("pm2_5", "median"),
                           pm2_5_max=("pm2_5", "max"),
                           pm10_mean=("pm10", "mean"),
                           aqi_mean=("us_aqi", "mean"),
                           aqi_max=("us_aqi", "max"),
                           hours_above_who=("above_who_pm2_5", "sum"),
                           share_above_who=("above_who_pm2_5", "mean"))
                      .round(2)
                      .sort_values("pm2_5_mean", ascending=False))
    print("\nGroupBy - statistics per city:")
    print(city_summary.to_string())

    hourly_pivot = df.pivot_table(index="city", columns="hour", values="pm2_5",
                                  aggfunc="mean", observed=True).round(1)
    print("\nPivot table - mean PM2.5 by city and hour (first 6 hours):")
    print(hourly_pivot.iloc[:, :6].to_string())

    long_format = df.melt(id_vars=["record_id", "city", "timestamp"],
                          value_vars=["pm2_5", "pm10"], var_name="pollutant", value_name="value")
    print(f"\nMelt - wide {df.shape} -> long {long_format.shape}")
    return city_summary, hourly_pivot


def clean(df):
    print(f"Records before cleaning: {len(df)}")
    df = df.copy()
    df = standardize_text(df)
    df = convert_types(df)
    df = remove_duplicates(df)
    df = handle_missing(df)
    df = add_features(df)
    show_filtering(df)
    city_summary, hourly_pivot = summarize(df)
    print(f"\nRecords after cleaning: {len(df)}")
    return df, city_summary, hourly_pivot


def save(df, city_summary, hourly_pivot):
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(CLEANED_CSV, index=False)
    city_summary.to_csv(CITY_SUMMARY_CSV)
    hourly_pivot.to_csv(HOURLY_PIVOT_CSV)
    print(f"Saved {CLEANED_CSV.name}, {CITY_SUMMARY_CSV.name}, {HOURLY_PIVOT_CSV.name}")


def run(valid_df=None):
    if valid_df is None:
        if not VALID_CSV.exists():
            sys.exit(f"{VALID_CSV.name} not found. Run the validator first: python -m src.validator")
        valid_df = pd.read_csv(VALID_CSV)
    cleaned, city_summary, hourly_pivot = clean(valid_df)
    save(cleaned, city_summary, hourly_pivot)
    return cleaned


if __name__ == "__main__":
    run()
