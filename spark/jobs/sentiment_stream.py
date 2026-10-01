"""
Job de Spark Structured Streaming: Kafka -> divide y venceras -> Postgres.

Flujo por micro-lote
--------------------
    1. Se leen los mensajes del topic y se parsea el JSON (esquema fijo:
       Structured Streaming exige esquema, no se infiere).
    2. ``foreachBatch`` reparte la particion entre los executors, que corren
       el clasificador divide y venceras y escriben las filas en ``mentions``.
    3. El driver espera a que todos los executors terminen, reconstruye la
       instantanea del grafo sobre la tabla completa y guarda la telemetria
       de complejidad del lote.

Por que ``foreachBatch`` y no ``foreach``
-----------------------------------------
El grafo y las estadisticas de complejidad son **agregados globales**: no se
pueden calcular por fila. ``foreachBatch`` da un DataFrame por lote, lo que
permite hacer la fase distribuida (mapPartitions) y la fase de driver
(recomputar el grafo) en el orden correcto.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402
from pyspark.sql.types import (  # noqa: E402
    ArrayType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from jobs.config import load_settings  # noqa: E402
from jobs.sinks import postgres as sink  # noqa: E402

LOG = logging.getLogger("sentiment_stream")

MESSAGE_SCHEMA = StructType(
    [
        StructField("mention_id", StringType(), True),
        StructField("ts", TimestampType(), True),
        StructField("brand", StringType(), True),
        StructField("author", StringType(), True),
        StructField("platform", StringType(), True),
        StructField("text", StringType(), True),
        StructField("lang", StringType(), True),
        StructField("hashtags", ArrayType(StringType()), True),
        StructField("author_followers", IntegerType(), True),
        StructField("likes", IntegerType(), True),
        StructField("shares", IntegerType(), True),
        StructField("expected", StringType(), True),
    ]
)


def build_spark() -> SparkSession:
    return (
        SparkSession.builder.appName("BrandPulse :: live sentiment")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.streaming.schemaInference", "false")
        .getOrCreate()
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [SPARK] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    settings = load_settings()
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_brokers)
        .option("subscribe", settings.kafka_topic)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", "5000")
        .load()
    )

    mentions = (
        raw.select(F.from_json(F.col("value").cast("string"), MESSAGE_SCHEMA).alias("m"))
        .select("m.*")
        .filter(F.col("mention_id").isNotNull() & F.col("text").isNotNull())
    )

    dsn = sink.dsn(settings)

    def process_batch(batch_df, batch_id: int) -> None:
        batch_df.persist()
        try:
            if batch_df.rdd.isEmpty():
                return

            counters = batch_df.rdd.mapPartitions(
                lambda rows: sink.analyze_partition(rows, dsn)
            ).reduce(lambda left, right: left + right)

            sink.refresh_snapshot(dsn, settings.graph_limit)
            sink.record_batch(dsn, settings.brand, int(batch_id), counters)

            summary = counters.as_dict()
            LOG.info(
                "lote %s | mensajes=%s exactitud=%.2f%% comparaciones=%s "
                "(teorico>=%s) mezclas=%s niveles=%s",
                batch_id,
                summary["messages"],
                summary["accuracy"],
                summary["comparisons"],
                summary["theoretical_min"],
                summary["merges"],
                summary["levels"],
            )
        finally:
            batch_df.unpersist()

    query = (
        mentions.writeStream.foreachBatch(process_batch)
        .outputMode("append")
        .trigger(processingTime=f"{settings.trigger_seconds} seconds")
        .option("checkpointLocation", settings.checkpoint_dir)
        .start()
    )

    LOG.info(
        "Escuchando topic '%s' en %s (marca=%s, trigger=%ss)",
        settings.kafka_topic,
        settings.kafka_brokers,
        settings.brand,
        settings.trigger_seconds,
    )
    query.awaitTermination()
    return 0


if __name__ == "__main__":
    sys.exit(main())
