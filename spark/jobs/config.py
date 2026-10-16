"""Configuracion del job de Spark, leida del entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseConfig:
    """Configuracion de PostgreSQL; se construye desde variables de entorno."""

    host: str
    port: int
    database: str
    username: str
    password: str
    batch_size: int = 500

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "brandpulse"),
            username=os.getenv("POSTGRES_USER", "marketing"),
            password=os.getenv("POSTGRES_PASSWORD", "marketing"),
            batch_size=int(os.getenv("DB_BATCH_SIZE", "500")),
        )

    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.username} password={self.password}"
        )


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        return cls(
            uri=os.getenv("NEO4J_URI", "neo4j://neo4j:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "brandpulse123"),
        )


@dataclass(frozen=True)
class Settings:
    kafka_brokers: str
    kafka_topic: str
    brand: str
    trigger_seconds: int
    checkpoint_dir: str

    database: DatabaseConfig
    neo4j: Neo4jConfig

    graph_limit: int


def load_settings() -> Settings:
    return Settings(
        kafka_brokers=os.getenv("KAFKA_BROKERS", "kafka:9092"),
        kafka_topic=os.getenv("KAFKA_TOPIC", "menciones"),
        brand=os.getenv("BRAND", "Nike"),
        trigger_seconds=int(os.getenv("SPARK_TRIGGER", "10")),
        checkpoint_dir=os.getenv("CHECKPOINT_DIR", "/tmp/brandpulse-checkpoint"),
        database=DatabaseConfig.from_env(),
        neo4j=Neo4jConfig.from_env(),
        graph_limit=int(os.getenv("GRAPH_LIMIT", "90")),
    )
