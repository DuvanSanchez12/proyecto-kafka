"""
Productor: simula la API de una plataforma social y publica menciones
de la marca al topic de Kafka en tiempo real.

En produccion este modulo se reemplaza por el cliente real de X o Reddit;
la contraparte (Spark Structured Streaming) no cambia porque el contrato
es el mismo: JSON con la clave ``mention_id`` en el valor del mensaje.
"""

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


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [PRODUCER] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    producer = Producer(
        {
            "bootstrap.servers": BROKERS,
            "client.id": f"brandpulse-producer-{uuid.uuid4().hex[:6]}",
            "linger.ms": 20,
            "batch.num.messages": 500,
            "acks": "1",
            "compression.type": "snappy",
            "queue.buffering.max.messages": 200000,
        }
    )

    LOG.info("Conectando a Kafka en %s (topic=%s)", BROKERS, TOPIC)
    while True:
        producer.poll(0)
        if not producer.list_topics(timeout=5).topics:
            LOG.warning("Kafka aun no responde, reintentando...")
            time.sleep(3)
            continue
        break
    LOG.info("Kafka disponible. Publicando menciones de '%s' a %d msg/s", BRAND, int(RATE))

    authors = build_author_pool(AUTHOR_POOL_SIZE)
    interval = 1.0 / max(RATE, 0.1)
    sent = 0
    next_tick = time.perf_counter()

    while _running:
        payload = corpus.make_mention(BRAND, authors, random.choice(PLATFORMS))
        message = {
            "mention_id": uuid.uuid4().hex,
            "ts": datetime.now(timezone.utc).isoformat(),
            "brand": BRAND,
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


if __name__ == "__main__":
    sys.exit(main())