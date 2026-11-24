# Air Quality in Kazakhstan Cities - Data Streaming and Validation Pipeline

SIS2 project for the course **Data Collection & Preparation**.

The pipeline collects hourly air quality data (PM2.5, PM10, US AQI) for 5 cities of Kazakhstan - Almaty, Astana, Shymkent, Atyrau and Karaganda - for the last 7 days from the Open-Meteo Air Quality API, streams the records through Apache Kafka and saves the consumed data for validation, cleaning, database storage and analysis.

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

**Option 2 - step by step:**

```bash
python -m src.api_client
python -m src.producer --use-saved
python -m src.consumer
```

| Step | What it does | Output |
|---|---|---|
| `src.api_client` | sends requests to the API for 5 cities | `data/raw_data.csv`, `data/raw_data.json` (original data) |
| `src.producer` | creates the topic and sends every record as a JSON message; key = `record_id` | number of published messages |
| `src.consumer` | reads JSON messages from the topic and converts them back to records | `data/consumed_data.csv`, number of consumed messages |

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

Published to Kafka: 840
Consumed from Kafka: 840
```

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
│   └── consumer.py
├── data/
└── docs/
    └── data_dictionary.md
```
