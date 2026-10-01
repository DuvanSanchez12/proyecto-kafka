"""Configuracion del job de Spark, leida del entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    kafka_brokers: str
    kafka_topic: str
    brand: str
    trigger_seconds: int
    checkpoint_dir: str

    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str

    # Numero de nodos del grafo que se conservan por tipo (los de mayor peso).
    graph_limit: int


def load_settings() -> Settings:
    return Settings(
        kafka_brokers=os.getenv("KAFKA_BROKERS", "kafka:9092"),
        kafka_topic=os.getenv("KAFKA_TOPIC", "menciones"),
        brand=os.getenv("BRAND", "Nike"),
        trigger_seconds=int(os.getenv("SPARK_TRIGGER", "10")),
        checkpoint_dir=os.getenv("CHECKPOINT_DIR", "/tmp/brandpulse-checkpoint"),
        pg_host=os.getenv("POSTGRES_HOST", "postgres"),
        pg_port=int(os.getenv("POSTGRES_PORT", "5432")),
        pg_db=os.getenv("POSTGRES_DB", "brandpulse"),
        pg_user=os.getenv("POSTGRES_USER", "marketing"),
        pg_password=os.getenv("POSTGRES_PASSWORD", "marketing"),
        graph_limit=int(os.getenv("GRAPH_LIMIT", "90")),
    )
