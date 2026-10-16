"""Base compartida por los dos productores de BrandPulse."""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import KafkaError, Producer

from . import corpus

LOG = logging.getLogger("producer")

BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "menciones")
BRAND = os.getenv("BRAND", "Nike")
RATE = float(os.getenv("PRODUCER_RATE", "25"))
PLATFORMS = [p.strip() for p in os.getenv("PLATFORMS", "x,reddit,instagram").split(",") if p.strip()]
AUTHOR_POOL_SIZE = int(os.getenv("AUTHOR_POOL_SIZE", "220"))
SOURCE = os.getenv("PRODUCER_SOURCE", "simulador")
PRODUCER_ID = os.getenv("PRODUCER_ID", "brandpulse-producer")

_running = True


def _stop(signum, _frame):  # pragma: no cover - senal del sistema
    global _running
    LOG.info("Senal %s recibida, cerrando productor...", signum)
    _running = False


def _delivery(err, msg):
    if err is not None:
        LOG.error("Entrega fallida: %s", err)
    else:
        LOG.debug("Publicado %s en %s", msg.key(), msg.topic())


def build_author_pool(size: int) -> list[str]:
    """Poblado estable de autores para que el grafo tenga comunidad."""
    pool = []
    for i in range(size):
        handle = f"user_{i:04d}"
        if random.random() < 0.12:
            handle = f"{corpus.random.choice(['tecno', 'gamer', 'moda', 'viajera', 'chef'])}_{i:03d}"
        pool.append(handle)
    return pool


class MentionProducer:
    """Productor Kafka configurable mediante argumentos de constructor."""

    def __init__(self, source: str, platforms: list[str], rate: float | None = None):
        self.source = source
        self.platforms = platforms
        self.rate = RATE if rate is None else rate
        self.producer = Producer(
            {
                "bootstrap.servers": BROKERS,
                "client.id": f"{PRODUCER_ID}-{uuid.uuid4().hex[:6]}",
                "linger.ms": 20,
                "batch.num.messages": 500,
                "acks": "1",
                "compression.type": "snappy",
                "queue.buffering.max.messages": 200000,
            }
        )

    def run(self) -> int:
        return run_producer(self.producer, self.source, self.platforms, self.rate)


def run_producer(producer: Producer, source: str, platforms: list[str], rate: float) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [PRODUCER] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    LOG.info("Conectando a Kafka en %s (topic=%s)", BROKERS, TOPIC)
    while True:
        producer.poll(0)
        if not producer.list_topics(timeout=5).topics:
            LOG.warning("Kafka aun no responde, reintentando...")
            time.sleep(3)
            continue
        break
    LOG.info("Kafka disponible. Fuente=%s marca='%s' ritmo=%d msg/s", source, BRAND, int(rate))

    authors = build_author_pool(AUTHOR_POOL_SIZE)
    interval = 1.0 / max(rate, 0.1)
    sent = 0
    next_tick = time.perf_counter()

    while _running:
        payload = corpus.make_mention(BRAND, authors, random.choice(platforms))
        message = {
            "mention_id": uuid.uuid4().hex,
            "ts": datetime.now(timezone.utc).isoformat(),
            "brand": BRAND,
            "source": source,
            **payload,
        }
        try:
            producer.produce(
                TOPIC,
                key=message["mention_id"].encode(),
                value=json.dumps(message, ensure_ascii=False).encode(),
                on_delivery=_delivery,
            )
            sent += 1
        except BufferError:
            producer.flush(2)
            continue

        producer.poll(0)
        next_tick += interval
        sleep = next_tick - time.perf_counter()
        if sleep > 0:
            time.sleep(sleep)
        elif sleep < -1:
            next_tick = time.perf_counter()

        if sent % 500 == 0:
            LOG.info("%d menciones publicadas", sent)

    producer.flush(10)
    LOG.info("Productor detenido tras %d mensajes", sent)
    return 0


def main() -> int:
    """Punto de entrada compatible para ejecucion manual del productor base."""
    return MentionProducer(SOURCE, PLATFORMS).run()


if __name__ == "__main__":
    sys.exit(main())
