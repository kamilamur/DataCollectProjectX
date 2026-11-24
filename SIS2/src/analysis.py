import sqlite3
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.config import CITIES, DB_PATH, DOCS_DIR, EDA_RESULTS_MD, FIGURES_DIR, WHO_PM25_24H

CITY_COLORS = dict(zip(CITIES, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]))
AQI_COLORS = {"Good": "#0ca30c", "Moderate": "#fab219",
              "Unhealthy for sensitive groups": "#ec835a", "Unhealthy": "#d03b3b",
              "Very unhealthy": "#8f2a7a", "Hazardous": "#5c1a1a"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.titleweight": "bold", "font.size": 10,
})


def load_from_db():
    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH.name} not found. Run the loader first: python -m src.loader")
    with sqlite3.connect(DB_PATH) as connection:
        df = pd.read_sql_query("SELECT * FROM air_quality", connection)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["collected_at"] = pd.to_datetime(df["collected_at"])
    df["date"] = pd.to_datetime(df["date"])
    df["city"] = pd.Categorical(df["city"], categories=list(CITIES))
    for column in ["is_weekend", "above_who_pm2_5", "above_who_pm10"]:
        df[column] = df[column].astype(bool)
    return df


def describe(df):
    print(f"Dataset shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print("\nData types:")
    print(df.dtypes.to_string())
    print("\nDescriptive statistics (numerical):")
    print(df[["pm2_5", "pm10", "us_aqi", "pm_ratio"]].describe().round(2).to_string())
    print("\nSkewness:")
    print(df[["pm2_5", "pm10", "us_aqi"]].skew().round(2).to_string())
    print("\nCorrelation:")
    print(df[["pm2_5", "pm10", "us_aqi"]].corr().round(3).to_string())
    print("\nCategorical - records per city:")
    print(df["city"].value_counts().to_string())
    print("\nCategorical - AQI category:")
    print(df["aqi_category"].value_counts().to_string())


def grouped(df):
    by_city = (df.groupby("city", observed=True)
                 .agg(pm2_5_mean=("pm2_5", "mean"), pm2_5_std=("pm2_5", "std"),
                      pm2_5_max=("pm2_5", "max"), aqi_mean=("us_aqi", "mean"),
                      share_above_who=("above_who_pm2_5", "mean"))
                 .round(2).sort_values("pm2_5_mean", ascending=False))
    by_period = df.assign(period=np.select(
        [df["hour"].between(6, 11), df["hour"].between(12, 17), df["hour"].between(18, 23)],
        ["morning", "day", "evening"], default="night"))
    by_period = (by_period.pivot_table(index="city", columns="period", values="pm2_5",
                                       aggfunc="mean", observed=True)
                          [["night", "morning", "day", "evening"]].round(1))
    weekday_weekend = (df.groupby(["city", "is_weekend"], observed=True)["pm2_5"].mean()
                         .unstack().rename(columns={False: "weekday", True: "weekend"}).round(1))
    print("\nGrouped - per city:")
    print(by_city.to_string())
    print("\nGrouped - mean PM2.5 by time of day:")
    print(by_period.to_string())
    print("\nGrouped - weekday vs weekend mean PM2.5:")
    print(weekday_weekend.to_string())
    return by_city, by_period


def save(fig, name):
    path = FIGURES_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved figures/{name}")
    return path


def plot_daily_trend(df):
    daily = df.groupby(["date", "city"], observed=True)["pm2_5"].mean().unstack()
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for city in daily.columns:
        ax.plot(daily.index, daily[city], color=CITY_COLORS[city], linewidth=2,
                marker="o", markersize=5, label=city)
    last_values = daily.iloc[-1].sort_values()
    label_y, min_gap = [], (daily.max().max()) * 0.045
    for value in last_values:
        label_y.append(max(value, label_y[-1] + min_gap) if label_y else value)
    for city, y in zip(last_values.index, label_y):
        ax.annotate(city, (daily.index[-1], y), xytext=(8, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=9)
    ax.hlines(WHO_PM25_24H, daily.index[0], daily.index[-1], color=MUTED, linestyle="--", linewidth=1)
    ax.text(daily.index[0], WHO_PM25_24H + 0.6, f"WHO 24-h guideline ({WHO_PM25_24H:g} μg/m³)",
            color=MUTED, fontsize=8)
    ax.set_title("Daily mean PM2.5 by city")
    ax.set_xlabel("Date")
    ax.set_ylabel("PM2.5, μg/m³")
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d %b"))
    ax.legend(title="City", loc="upper center", bbox_to_anchor=(0.5, -0.15), frameon=False, ncol=5)
    return save(fig, "1_daily_pm25_trend.png"), daily


def plot_distribution(df):
    order = df.groupby("city", observed=True)["pm2_5"].median().sort_values(ascending=False).index
    fig, ax = plt.subplots(figsize=(9, 5.5))
    sns.boxplot(data=df, x="city", y="pm2_5", hue="city", order=list(order), palette=CITY_COLORS,
                legend=False, width=0.55, linewidth=1, fliersize=3, ax=ax)
    ax.axhline(WHO_PM25_24H, color=MUTED, linestyle="--", linewidth=1, label="WHO 24-h guideline")
    ax.set_title("Distribution of hourly PM2.5 by city")
    ax.set_xlabel("City (sorted by median)")
    ax.set_ylabel("PM2.5, μg/m³")
    ax.legend(loc="upper right", frameon=False)
    return save(fig, "2_pm25_distribution_by_city.png")


def plot_hour_heatmap(df):
    pivot = df.pivot_table(index="city", columns="hour", values="pm2_5", aggfunc="mean",
                           observed=True)
    fig, ax = plt.subplots(figsize=(12, 4))
    sns.heatmap(pivot, cmap="Blues", annot=True, fmt=".0f", annot_kws={"fontsize": 7},
                linewidths=1, linecolor="#fcfcfb",
                cbar_kws={"label": "Mean PM2.5, μg/m³"}, ax=ax)
    ax.set_title("Mean PM2.5 by hour of day (local time)")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("City")
    ax.tick_params(axis="y", rotation=0)
    ax.grid(False)
    return save(fig, "3_pm25_hour_heatmap.png"), pivot


def plot_aqi_categories(df):
    shares = pd.crosstab(df["city"], df["aqi_category"], normalize="index") * 100
    shares = shares[[c for c in AQI_COLORS if c in shares.columns]]
    shares = shares.sort_values(shares.columns[0], ascending=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.set_axisbelow(True)
    left = np.zeros(len(shares))
    for category in shares.columns:
        values = shares[category].to_numpy()
        ax.barh(shares.index.astype(str), values, left=left, color=AQI_COLORS[category],
                edgecolor="#fcfcfb", linewidth=2, label=category, height=0.6)
        for y, (start, width) in enumerate(zip(left, values)):
            if width >= 8:
                ax.text(start + width / 2, y, f"{width:.0f}%", ha="center", va="center",
                        color=INK, fontsize=8)
        left += values
    ax.set_title("Share of hours by US AQI category")
    ax.set_xlabel("Share of hours, %")
    ax.set_ylabel("City")
    ax.set_xlim(0, 100)
    ax.grid(axis="y", visible=False)
    ax.legend(title="AQI category", loc="upper center", bbox_to_anchor=(0.5, -0.18),
              ncol=len(shares.columns), frameon=False)
    return save(fig, "4_aqi_category_share.png"), shares


def write_findings(df, by_city, by_period, daily, hour_pivot, aqi_shares):
    worst, best = by_city.index[0], by_city.index[-1]
    peak_hours = hour_pivot.idxmax(axis=1)
    low_hours = hour_pivot.idxmin(axis=1)
    worst_day = daily.mean(axis=1).idxmax()
    corr = df[["pm2_5", "us_aqi"]].corr().iloc[0, 1]
    good_share = aqi_shares.get("Good", pd.Series(0, index=aqi_shares.index))
    lines = [
        "# EDA results",
        "",
        "Generated by `python -m src.analysis` from `data/output.db`. "
        "Numbers change when new data is collected.",
        "",
        f"- Period: {df['timestamp'].min():%Y-%m-%d %H:%M} - {df['timestamp'].max():%Y-%m-%d %H:%M}, "
        f"{len(df)} hourly records, {df['city'].nunique()} cities.",
        f"- Mean PM2.5 over all cities: {df['pm2_5'].mean():.1f} μg/m³ "
        f"(median {df['pm2_5'].median():.1f}); "
        f"{df['above_who_pm2_5'].mean():.0%} of hours are above the WHO guideline of {WHO_PM25_24H:g} μg/m³.",
        f"- Correlation between PM2.5 and US AQI: {corr:.2f}.",
        "",
        "## Figure 1 - daily mean PM2.5 (`figures/1_daily_pm25_trend.png`)",
        f"- {worst} has the highest weekly mean PM2.5 ({by_city.loc[worst, 'pm2_5_mean']} μg/m³), "
        f"{best} the lowest ({by_city.loc[best, 'pm2_5_mean']} μg/m³).",
        f"- The most polluted day on average was {worst_day:%d %b %Y}.",
        "- Lines above the dashed WHO line mean the daily average exceeded the guideline.",
        "",
        "## Figure 2 - distribution by city (`figures/2_pm25_distribution_by_city.png`)",
    ]
    for city, row in by_city.iterrows():
        lines.append(f"- {city}: mean {row['pm2_5_mean']}, std {row['pm2_5_std']}, max "
                     f"{row['pm2_5_max']} μg/m³, {row['share_above_who']:.0%} of hours above WHO.")
    lines += [
        "",
        "## Figure 3 - hour of day heatmap (`figures/3_pm25_hour_heatmap.png`)",
    ]
    for city in hour_pivot.index:
        lines.append(f"- {city}: highest at {peak_hours[city]:02d}:00 "
                     f"({hour_pivot.loc[city, peak_hours[city]]:.1f}), lowest at "
                     f"{low_hours[city]:02d}:00 ({hour_pivot.loc[city, low_hours[city]]:.1f}).")
    lines += [
        f"- Mean PM2.5 by time of day: "
        + "; ".join(f"{p} {by_period[p].mean():.1f}" for p in by_period.columns) + ".",
        "",
        "## Figure 4 - AQI categories (`figures/4_aqi_category_share.png`)",
    ]
    for city in aqi_shares.index:
        parts = ", ".join(f"{c} {aqi_shares.loc[city, c]:.0f}%" for c in aqi_shares.columns
                          if aqi_shares.loc[city, c] > 0)
        lines.append(f"- {city}: {parts}.")
    lines += [
        "",
        "## Conclusions",
        f"- Air quality differs strongly between cities: {worst} is about "
        f"{by_city.loc[worst, 'pm2_5_mean'] / by_city.loc[best, 'pm2_5_mean']:.1f}x more polluted "
        f"than {best} by mean PM2.5.",
        f"- The city with the most 'Good' AQI hours is {good_share.idxmax()} "
        f"({good_share.max():.0f}%); cities with no 'Good' hours at all: "
        f"{', '.join(map(str, good_share[good_share == 0].index)) or 'none'}.",
        "- Pollution follows a daily cycle, so the hour of day matters as much as the city.",
        "- Limitation: only 7 days of modelled (CAMS) data, so weather of that week has a large effect.",
    ]
    DOCS_DIR.mkdir(exist_ok=True)
    EDA_RESULTS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved docs/{EDA_RESULTS_MD.name}")
    print("\n".join(lines))


def run():
    FIGURES_DIR.mkdir(exist_ok=True)
    df = load_from_db()
    describe(df)
    by_city, by_period = grouped(df)
    print()
    _, daily = plot_daily_trend(df)
    plot_distribution(df)
    _, hour_pivot = plot_hour_heatmap(df)
    _, aqi_shares = plot_aqi_categories(df)
    print()
    write_findings(df, by_city, by_period, daily, hour_pivot, aqi_shares)


if __name__ == "__main__":
    run()
