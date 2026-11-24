import json
import sys

import pandas as pd
from kafka import KafkaConsumer
from kafka.errors import KafkaError

from src.config import CONSUMED_CSV, DATA_DIR, KAFKA_GROUP, KAFKA_SERVER, KAFKA_TOPIC


def read_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def consume(max_messages=None):
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_SERVER,
        group_id=KAFKA_GROUP,
        auto_offset_reset="earliest",
        consumer_timeout_ms=15000,
    )
    records, failed = [], 0
    for message in consumer:
        record = read_json(message.value)
        if record is None:
            failed += 1
        else:
            records.append(record)
        if max_messages and len(records) + failed >= max_messages:
            break
    consumer.close()
    print(f"Consumed: {len(records)}, failed to read: {failed}")
    return records


def save_consumed(records):
    DATA_DIR.mkdir(exist_ok=True)
    pd.DataFrame(records).to_csv(CONSUMED_CSV, index=False)
    print(f"Saved consumed data to {CONSUMED_CSV.name}")


def run(max_messages=None):
    try:
        records = consume(max_messages)
    except KafkaError:
        sys.exit(f"Kafka is not running on {KAFKA_SERVER}. Start it: docker compose up -d")
    if records:
        save_consumed(records)
    return records


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run(limit)
