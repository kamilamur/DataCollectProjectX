from src import consumer, producer

sent = producer.run()
received = consumer.run(max_messages=sent)
print(f"\nPublished to Kafka: {sent}")
print(f"Consumed from Kafka: {len(received)}")
