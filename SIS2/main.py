import sys

import pandas as pd

from src import analysis, cleaner, consumer, loader, producer, validator
from src.config import CONSUMED_CSV, RAW_JSON


def stage(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main(skip_kafka=False):
    if skip_kafka:
        stage("Stages 1-2 skipped: using data/consumed_data.csv from the last Kafka run")
        collected = len(pd.read_json(RAW_JSON)) if RAW_JSON.exists() else None
        received = pd.read_csv(CONSUMED_CSV).to_dict("records")
        sent = None
    else:
        stage("Stages 1-2: API collection and Kafka producer")
        sent = producer.run()
        collected = len(pd.read_json(RAW_JSON))
        stage("Stage 2: Kafka consumer")
        received = consumer.run(max_messages=sent)
        if not received:
            sys.exit("No messages were consumed, pipeline stopped.")

    stage("Stage 3: Pandera validation")
    valid, invalid = validator.run(received)

    stage("Stage 4: cleaning and transformation")
    cleaned = cleaner.run(valid)

    stage("Stage 5: SQLite storage (loaded twice to prove idempotency)")
    stored = loader.run(cleaned, times=2)

    stage("Stage 6: EDA and visualization")
    analysis.run()

    stage("Stage 7: pipeline summary")
    invalid_real = int((~invalid["is_test"]).sum())
    invalid_test = int(invalid["is_test"].sum())
    counts = [
        ("Collected from API", collected),
        ("Published to Kafka", sent),
        ("Consumed from Kafka", len(received)),
        ("Valid records", len(valid)),
        ("Invalid records (real data)", invalid_real),
        ("Invalid test records (excluded)", invalid_test),
        ("Records after cleaning", len(cleaned)),
        ("Records stored in SQLite", stored),
    ]
    for name, value in counts:
        print(f"{name:<34}{'-' if value is None else value:>8}")
    print("\nDifferences: invalid real records are quarantined in data/invalid_records.csv; "
          "cleaning removes duplicates and rows with long gaps; the database keeps records "
          "from earlier runs, so it can hold more rows than the current run processed.")


if __name__ == "__main__":
    main(skip_kafka="--skip-kafka" in sys.argv)
