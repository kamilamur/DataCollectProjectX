# Air Quality in Kazakhstan Cities - Data Streaming and Validation Pipeline

SIS2 project for the course **Data Collection & Preparation**.

The pipeline collects hourly air quality data (PM2.5, PM10, US AQI) for 5 cities of Kazakhstan - Almaty, Astana, Shymkent, Atyrau and Karaganda - for the last 7 days from the Open-Meteo Air Quality API, streams the records through Apache Kafka, validates them with Pandera, cleans and transforms them with pandas and NumPy, stores them in SQLite3 and performs exploratory data analysis.

```
Open-Meteo API -> api_client -> producer -> Kafka topic -> consumer -> validator (Pandera)
               -> cleaner (pandas/NumPy) -> loader (SQLite3) -> analysis (EDA + figures)
```

## Requirements

- Python 3.10 or newer
- Docker Desktop (for the Kafka broker)
- Internet connection (for the API)

```bash
pip install -r requirements.txt
```

## API

- Endpoint: `https://air-quality-api.open-meteo.com/v1/air-quality`
- No API key is needed.
- Request parameters for each city:

| Parameter | Value |
|---|---|
| latitude, longitude | city coordinates (see `src/config.py`) |
| hourly | `pm2_5,pm10,us_aqi` |
| past_days | `7` |
| forecast_days | `0` |
| timezone | `Asia/Almaty` |

One request returns 168 hourly values (7 days x 24 hours) for one city, so 5 cities give **840 records**.
Errors are handled in `src/api_client.py`: a failed request (timeout, connection error, status code other than 200, response without data) is repeated up to 3 times, and the city is skipped if all attempts fail.

## Kafka setup

Start the Kafka broker in Docker (KRaft mode, no Zookeeper):

```bash
docker compose up -d
docker ps
```

The broker runs on `localhost:9092`.
The topic `kz_air_quality` (1 partition, replication factor 1) is created automatically by the producer. It can also be created or checked by hand:

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic kz_air_quality --partitions 1 --replication-factor 1
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Settings can be changed with environment variables (see `.env.example`): `KAFKA_SERVER`, `KAFKA_TOPIC`, `KAFKA_GROUP`.

## How to run

Run all commands from the project folder.

**Option 1 - full pipeline:**

```bash
python main.py
```

`main.py` runs every stage in order, loads the database twice (idempotency test) and prints a summary of the record counts of all stages.
`python main.py --skip-kafka` re-runs only stages 3-7 on `data/consumed_data.csv` from the last Kafka run (useful when Kafka is stopped).

**Option 2 - step by step:**

```bash
python -m src.api_client
python -m src.producer --use-saved
python -m src.consumer
python -m src.validator
python -m src.cleaner
python -m src.loader
python -m src.analysis
```

| Step | What it does | Output |
|---|---|---|
| `src.api_client` | sends requests to the API for 5 cities | `data/raw_data.csv`, `data/raw_data.json` (original data) |
| `src.producer` | creates the topic and sends every record as a JSON message; key = `record_id` | number of published messages |
| `src.consumer` | reads JSON messages from the topic and converts them back to records | `data/consumed_data.csv`, number of consumed messages |
| `src.validator` | checks the consumed data with a Pandera schema (9 rules) plus 5 deliberately invalid test records | `data/validated_data.csv`, `data/invalid_records.csv`, valid/invalid counts |
| `src.cleaner` | text normalization, type conversion, duplicate removal, missing values, NumPy features, filtering, GroupBy, pivot_table / melt | `data/cleaned_data.csv`, `data/city_summary.csv`, `data/city_hour_pivot.csv` |
| `src.loader` | creates `data/output.db`, inserts the cleaned data **twice**, checks that the second run adds nothing, runs SQL verification queries | `data/output.db` |
| `src.analysis` | reads the database, prints descriptive / categorical / grouped statistics, draws 4 figures, writes findings | `figures/*.png`, `docs/eda_results.md` |

`python -m src.loader --once` loads only one time.

## Validation (Pandera)

Schema `air_quality_schema` in `src/validator.py`:

1. `record_id` is required and has the format `City_YYYY-MM-DDTHH:MM`
2. `city` is one of the 5 cities (case and extra spaces are ignored, they are fixed in cleaning)
3. `latitude` / `longitude` are inside Kazakhstan
4. `timestamp` and `collected_at` are valid date/times, `timestamp` is not before 2013
5. `pm2_5` in [0, 1000], `pm10` in [0, 2000] μg/m³ (missing values are allowed and handled in cleaning)
6. `us_aqi` is a whole number in [0, 500]
7. `pm10 >= pm2_5` (PM10 contains PM2.5)
8. `timestamp` is not after `collected_at`
9. `record_id` equals `city + "_" + timestamp`

The real API data has no errors, so 5 deliberately invalid **test records** (`is_test = True`) are added before validation. All errors are collected with `lazy=True`. Invalid records are not deleted silently: they are saved with their error messages in `data/invalid_records.csv`, and only valid, non-test records go to cleaning.

## Cleaning and transformation

| Operation | Why |
|---|---|
| `city` strip + title case | one spelling per city for grouping |
| `timestamp`, `collected_at` -> datetime, `city` -> category, numbers -> numeric | correct sorting, date features and calculations |
| drop exact duplicates and duplicates by `record_id` (keep the latest `collected_at`) | the same hour can be consumed twice if the producer is run again |
| interpolate gaps of up to 3 hours inside each city, drop rows with longer gaps | hourly series are smooth, but long gaps cannot be guessed |
| NumPy: `pm_ratio` (`np.where`), `log_pm2_5` (`np.log1p`), z-score per city, WHO flags, AQI category (`np.digitize`) | features for analysis and outlier detection |
| filtering with several conditions | weekday evening hours with PM2.5 > 35; unusual values |
| GroupBy + agg, `pivot_table`, `melt` | statistics per city, city x hour table, long format |

## Database

`data/output.db`, table `air_quality`: `record_id` is the PRIMARY KEY and `(city, timestamp)` is UNIQUE. Rows are inserted with `INSERT ... ON CONFLICT DO NOTHING`, so repeated runs never create duplicates. Every load is written to the table `load_log`. Schema details: `docs/data_dictionary.md`.

Check the database by hand:

```bash
python -c "import sqlite3; c = sqlite3.connect('data/output.db'); print(c.execute('SELECT city, COUNT(*) FROM air_quality GROUP BY city').fetchall())"
```

`--use-saved` sends the records from `data/raw_data.json`. Without it the producer collects new data from the API first.

The consumer stops when no new message comes for 15 seconds. `python -m src.consumer 840` stops after 840 messages.
The consumer uses the group `air-quality-consumer`, so Kafka remembers which messages were already read: a second run of the consumer reads only new messages.

## Expected output

```
Almaty: 168 records
Astana: 168 records
Shymkent: 168 records
Atyrau: 168 records
Karaganda: 168 records
Total collected: 840
Topic 'kz_air_quality' created
Published: 840, failed: 0
Consumed: 840, failed to read: 0
...
Valid: 840, invalid: 5 (real: 0, test records caught: 5/5)
...
Records after cleaning: 840
...
Load run 1:
Processed: 840, inserted: 840, skipped as duplicates: 0, rows in table: 840
Load run 2:
Processed: 840, inserted: 0, skipped as duplicates: 840, rows in table: 840
Idempotency check: repeated load inserted 0 rows, table content unchanged: True -> PASSED
...
Collected from API                     840
Published to Kafka                     840
Consumed from Kafka                    840
Valid records                          840
Invalid records (real data)              0
Invalid test records (excluded)          5
Records after cleaning                 840
Records stored in SQLite               840
```

Successful execution: the summary counts match, the idempotency check says `PASSED`, the SQL query "Duplicate city+hour" returns no rows, and `figures/` contains 4 PNG files.
If the pipeline is run again on another day, new hours are added to the database and old ones are skipped, so "stored in SQLite" can be larger than "after cleaning".

## Stop Kafka

```bash
docker compose down
```

## Project structure

```
├── docker-compose.yml
├── requirements.txt
├── main.py
├── .env.example
├── src/
│   ├── config.py
│   ├── api_client.py
│   ├── producer.py
│   ├── consumer.py
│   ├── validator.py
│   ├── cleaner.py
│   ├── loader.py
│   └── analysis.py
├── data/          raw, consumed, validated, invalid, cleaned CSVs and output.db
├── figures/       EDA figures
└── docs/
    ├── data_dictionary.md
    └── eda_results.md
```
