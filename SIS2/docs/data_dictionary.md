# Data Dictionary

Raw records collected from the Open-Meteo Air Quality API (`data/raw_data.csv`) and consumed from Kafka (`data/consumed_data.csv`).

| Column | Type | Kind | Description | Example |
|---|---|---|---|---|
| record_id | string | identifier | unique id: city + hour | `Almaty_2026-11-17T00:00` |
| city | string | categorical | one of: Almaty, Astana, Shymkent, Atyrau, Karaganda | `Almaty` |
| latitude | float | numerical | latitude of the API grid point | `43.199997` |
| longitude | float | numerical | longitude of the API grid point | `76.899994` |
| timestamp | string (ISO date/time) | date/time | hour of the measurement, local time (Asia/Almaty) | `2026-11-17T00:00` |
| pm2_5 | float | numerical | fine particles, diameter below 2.5 μm, μg/m³ | `24.9` |
| pm10 | float | numerical | particles, diameter below 10 μm, μg/m³ | `25.6` |
| us_aqi | integer | numerical | US Air Quality Index (0-500, higher = worse air) | `82` |
| collected_at | string (ISO date/time) | date/time | when the data was collected | `2026-11-24T16:05:24` |

## US AQI levels

| AQI | Level |
|---|---|
| 0-50 | Good |
| 51-100 | Moderate |
| 101-150 | Unhealthy for sensitive groups |
| 151-200 | Unhealthy |
| 201-300 | Very unhealthy |
| 301-500 | Hazardous |
