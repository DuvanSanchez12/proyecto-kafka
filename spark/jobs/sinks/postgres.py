"""
Sumidero Postgres del job de streaming.

Divide el trabajo en dos mitades con responsabilidades distintas:

* ``analyze_partition`` corre **en cada executor** (via ``mapPartitions``):
  clasifica las menciones con el divide y venceras, ordena los items de
  opinion con merge sort y escribe las filas. Devuelve los contadores de
  complejidad de su particion.
* ``refresh_snapshot`` y ``record_batch`` corren **en el driver**: reconstruyen
  la instantanea del grafo y guardan la telemetria del micro-lote una vez que
  todos los executors terminaron de escribir.

Esa separacion es intencional: el grafo se arma sobre la tabla completa, que
solo esta consistente despues del commit de todos los executors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Iterator

import psycopg2
from psycopg2.extras import execute_values

from ..algorithms.complexity import (
    ComplexityMeter,
    theoretical_merge_comparisons,
)
from ..algorithms.merge_sort import merge_sort
from ..algorithms.sentiment_dnc import analyze
from ..config import Settings
from ..graph.builder import BUCKETS_SQL, refresh_sql

INSERT_MENTION = """
INSERT INTO mentions (
    mention_id, ts, brand, platform, author, author_followers, text, lang,
    hashtags, keywords, sentiment, score, confidence,
    dnc_comparisons, dnc_levels, sort_comparisons, expected, likes, shares
) VALUES %s
ON CONFLICT (mention_id) DO NOTHING
"""

INSERT_STATS = """
INSERT INTO complexity_stats (
    batch_index, messages, total_tokens, dnc_comparisons, dnc_levels,
    sort_comparisons, theoretical_min, merge_operations
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (batch_index) DO UPDATE SET
    processed_at      = now(),
    messages          = EXCLUDED.messages,
    total_tokens      = EXCLUDED.total_tokens,
    dnc_comparisons   = EXCLUDED.dnc_comparisons,
    dnc_levels        = EXCLUDED.dnc_levels,
    sort_comparisons  = EXCLUDED.sort_comparisons,
    theoretical_min   = EXCLUDED.theoretical_min,
    merge_operations  = EXCLUDED.merge_operations
"""

UPSERT_STATE = """
INSERT INTO pipeline_state (id, brand, last_batch, last_updated)
VALUES (1, %s, %s, now())
ON CONFLICT (id) DO UPDATE SET
    brand        = EXCLUDED.brand,
    last_batch   = EXCLUDED.last_batch,
    last_updated = now()
"""


@dataclass
class Counters:
    """Contadores de complejidad de una particion o de un micro-lote."""

    messages: int = 0
    tokens: int = 0
    comparisons: int = 0
    levels: int = 0
    merges: int = 0
    sort_comparisons: int = 0
    theoretical_min: int = 0
    correct: int = 0
    pos: int = 0
    neu: int = 0
    neg: int = 0

    def __add__(self, other: "Counters") -> "Counters":
        return Counters(
            messages=self.messages + other.messages,
            tokens=self.tokens + other.tokens,
            comparisons=self.comparisons + other.comparisons,
            levels=max(self.levels, other.levels),
            merges=self.merges + other.merges,
            sort_comparisons=self.sort_comparisons + other.sort_comparisons,
            theoretical_min=self.theoretical_min + other.theoretical_min,
            correct=self.correct + other.correct,
            pos=self.pos + other.pos,
            neu=self.neu + other.neu,
            neg=self.neg + other.neg,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "tokens": self.tokens,
            "comparisons": self.comparisons,
            "levels": self.levels,
            "merges": self.merges,
            "sort_comparisons": self.sort_comparisons,
            "theoretical_min": self.theoretical_min,
            "accuracy": round(100.0 * self.correct / self.messages, 2) if self.messages else 0.0,
            "positivos": self.pos,
            "neutrales": self.neu,
            "negativos": self.neg,
        }


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "asDict"):
        return row.asDict(recursive=True)
    return dict(row)


def analyze_partition(rows: Iterable[Any], dsn: str) -> Iterator[Counters]:
    """
    Clasifica y escribe una particion. Corre en el executor.

    Cada llamada abre su propia conexion (las conexiones de psycopg2 no se
    pueden serializar entre el driver y los executors) y hace un unico commit
    al final, con insercion por lotes.
    """
    conn = psycopg2.connect(dsn)
    counters = Counters()
    payload: list[tuple] = []
    try:
        for row in rows:
            mention = _row_to_dict(row)
            text = mention.get("text") or ""
            result = analyze(text)

            sort_meter = ComplexityMeter()
            merge_sort(
                result.opinions,
                key=lambda o: abs(o.signed_weight),
                reverse=True,
                meter=sort_meter,
            )
            sort_comparisons = sort_meter.comparisons

            expected = mention.get("expected")
            correct = bool(expected) and expected == result.sentiment

            payload.append(
                (
                    mention.get("mention_id"),
                    mention.get("ts"),
                    mention.get("brand"),
                    mention.get("platform"),
                    mention.get("author"),
                    int(mention.get("author_followers") or 0),
                    text,
                    mention.get("lang") or "es",
                    list(mention.get("hashtags") or []),
                    list(result.keywords),
                    result.sentiment,
                    float(result.score),
                    float(result.confidence),
                    int(result.meter.comparisons),
                    int(result.meter.max_depth),
                    int(sort_comparisons),
                    expected,
                    int(mention.get("likes") or 0),
                    int(mention.get("shares") or 0),
                )
            )

            counters.messages += 1
            counters.tokens += result.tokens
            counters.comparisons += result.meter.comparisons
            counters.levels = max(counters.levels, result.meter.max_depth)
            counters.merges += result.meter.merges
            counters.sort_comparisons += sort_comparisons
            counters.theoretical_min += theoretical_merge_comparisons(result.tokens)
            counters.correct += int(correct)
            if result.sentiment == "POSITIVO":
                counters.pos += 1
            elif result.sentiment == "NEGATIVO":
                counters.neg += 1
            else:
                counters.neu += 1

        if payload:
            with conn.cursor() as cur:
                execute_values(cur, INSERT_MENTION, payload, page_size=500)
        conn.commit()
    finally:
        conn.close()
    return iter([counters])


def refresh_snapshot(dsn: str, graph_limit: int, window_minutes: int = 20) -> None:
    """Reconstruye la instantanea del grafo y refresca la serie por minuto."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            for _label, sql in refresh_sql():
                cur.execute(sql, {"limit": graph_limit})
            cur.execute(BUCKETS_SQL, {"window": window_minutes})
        conn.commit()
    finally:
        conn.close()


def record_batch(dsn: str, brand: str, batch_index: int, counters: Counters) -> None:
    """Telemetria del micro-lote: complejidad + checkpoint logico del pipeline."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                INSERT_STATS,
                (
                    batch_index,
                    counters.messages,
                    counters.tokens,
                    counters.comparisons,
                    counters.levels,
                    counters.sort_comparisons,
                    counters.theoretical_min,
                    counters.merges,
                ),
            )
            cur.execute(UPSERT_STATE, (brand, batch_index))
        conn.commit()
    finally:
        conn.close()


def dsn(settings: Settings) -> str:
    return (
        f"host={settings.pg_host} port={settings.pg_port} dbname={settings.pg_db} "
        f"user={settings.pg_user} password={settings.pg_password}"
    )
