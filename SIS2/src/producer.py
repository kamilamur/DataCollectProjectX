import json
import sys

from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import KafkaError, TopicAlreadyExistsError

from src.api_client import collect_all, load_raw, save_raw
from src.config import KAFKA_SERVER, KAFKA_TOPIC, RAW_JSON


def create_topic():
    admin = KafkaAdminClient(bootstrap_servers=KAFKA_SERVER)
    try:
        admin.create_topics([NewTopic(name=KAFKA_TOPIC, num_partitions=1, replication_factor=1)])
        print(f"Topic '{KAFKA_TOPIC}' created")
    except TopicAlreadyExistsError:
        print(f"Topic '{KAFKA_TOPIC}' already exists")
    admin.close()


def send_records(records):
    producer = KafkaProducer(bootstrap_servers=KAFKA_SERVER)
    sent, failed = 0, 0
    for record in records:
        try:
            key = record["record_id"].encode("utf-8")
            value = json.dumps(record).encode("utf-8")
            producer.send(KAFKA_TOPIC, key=key, value=value).get(timeout=10)
            sent += 1
        except KafkaError as error:
            failed += 1
            print(f"Failed to send {record['record_id']}: {error}")
    producer.flush()
    producer.close()
    print(f"Published: {sent}, failed: {failed}")
    return sent


def run(use_saved=False):
    if use_saved and RAW_JSON.exists():
        records = load_raw()
    else:
        records = collect_all()
        save_raw(records)
    try:
        create_topic()
        return send_records(records)
    except KafkaError:
        sys.exit(f"Kafka is not running on {KAFKA_SERVER}. Start it: docker compose up -d")


if __name__ == "__main__":
    run(use_saved="--use-saved" in sys.argv)
