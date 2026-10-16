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

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

import psycopg2
from psycopg2.extras import execute_values

from ..algorithms.complexity import (
    ComplexityMeter,
    theoretical_merge_comparisons,
)
from ..algorithms.merge_sort import merge_sort
from ..algorithms.sentiment_dnc import analyze
from ..config import DatabaseConfig, Settings
from ..graph.builder import BUCKETS_SQL

INSERT_MENTION = """
INSERT INTO mentions (
    mention_id, ts, brand, source, platform, author, author_followers, text, lang,
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


# Contadores que se suman al combinar dos mapas de contribuciones.
_NODE_FIELDS = ("weight", "pos", "neu", "neg", "score_sum")
_EDGE_FIELDS = ("weight", "score_sum")


def _bump_node(nodes: dict, node_id: str, label: str, name: str, sentiment: str, score: float) -> None:
    entry = nodes.get(node_id)
    if entry is None:
        entry = {
            "node_id": node_id,
            "label": label,
            "name": name,
            "weight": 0,
            "pos": 0,
            "neu": 0,
            "neg": 0,
            "score_sum": 0.0,
        }
        nodes[node_id] = entry
    entry["weight"] += 1
    entry["score_sum"] += score
    if sentiment == "POSITIVO":
        entry["pos"] += 1
    elif sentiment == "NEGATIVO":
        entry["neg"] += 1
    else:
        entry["neu"] += 1


def _bump_edge(edges: dict, src: str, dst: str, rel: str, score: float) -> None:
    key = (src, dst, rel)
    entry = edges.get(key)
    if entry is None:
        entry = {"src": src, "dst": dst, "rel": rel, "weight": 0, "score_sum": 0.0}
        edges[key] = entry
    entry["weight"] += 1
    entry["score_sum"] += score


def _merge_maps(left: dict, right: dict, fields: tuple[str, ...]) -> dict:
    merged = {k: dict(v) for k, v in left.items()}
    for key, value in right.items():
        current = merged.get(key)
        if current is None:
            merged[key] = dict(value)
        else:
            for fname in fields:
                current[fname] += value[fname]
    return merged


@dataclass
class GraphDelta:
    """Contribuciones de un lote al grafo de co-ocurrencia (nodos y aristas)."""

    nodes: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)

    def __add__(self, other: "GraphDelta") -> "GraphDelta":
        return GraphDelta(
            nodes=_merge_maps(self.nodes, other.nodes, _NODE_FIELDS),
            edges=_merge_maps(self.edges, other.edges, _EDGE_FIELDS),
        )


@dataclass
class PartitionState:
    """Resultado de analizar una particion: telemetria + delta del grafo."""

    counters: Counters = field(default_factory=Counters)
    delta: GraphDelta = field(default_factory=GraphDelta)

    def __add__(self, other: "PartitionState") -> "PartitionState":
        return PartitionState(
            counters=self.counters + other.counters,
            delta=self.delta + other.delta,
        )


class BatchedPostgresWriter:
    """Persiste filas en PostgreSQL mediante lotes SQL configurables."""

    def __init__(self, config: DatabaseConfig):
        self.config = config

    def insert_mentions(self, rows: list[tuple]) -> None:
        if not rows:
            return
        conn = psycopg2.connect(self.config.dsn())
        try:
            with conn.cursor() as cur:
                execute_values(cur, INSERT_MENTION, rows, page_size=self.config.batch_size)
            conn.commit()
        finally:
            conn.close()


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "asDict"):
        return row.asDict(recursive=True)
    return dict(row)


def analyze_partition(rows: Iterable[Any], database: DatabaseConfig) -> Iterator[PartitionState]:
    """
    Clasifica y escribe una particion. Corre en el executor.

    Cada llamada abre su propia conexion (las conexiones de psycopg2 no se
    pueden serializar entre el driver y los executors) y hace un unico commit
    al final, con insercion por lotes.

    Ademas de los contadores de complejidad, acumula el **delta del grafo** de
    la particion (nodos y aristas con su peso y suma de sentimiento) para que el
    driver lo aplique de forma incremental en Neo4j.
    """
    counters = Counters()
    delta = GraphDelta()
    payload: list[tuple] = []
    writer = BatchedPostgresWriter(database)
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

        hashtags = list(mention.get("hashtags") or [])
        keywords = list(result.keywords)
        brand = mention.get("brand")

        payload.append(
            (
                mention.get("mention_id"),
                mention.get("ts"),
                brand,
                mention.get("source") or "desconocida",
                mention.get("platform"),
                mention.get("author"),
                int(mention.get("author_followers") or 0),
                text,
                mention.get("lang") or "es",
                hashtags,
                keywords,
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

        _accumulate_graph(
            delta,
            brand=brand,
            author=mention.get("author"),
            platform=mention.get("platform"),
            hashtags=hashtags,
            keywords=keywords,
            sentiment=result.sentiment,
            score=float(result.score),
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

    writer.insert_mentions(payload)
    return iter([PartitionState(counters=counters, delta=delta)])


def _accumulate_graph(
    delta: GraphDelta,
    *,
    brand: str | None,
    author: str | None,
    platform: str | None,
    hashtags: list[str],
    keywords: list[str],
    sentiment: str,
    score: float,
) -> None:
    """Traduce una mencion a contribuciones del grafo (mismo modelo que la API)."""
    u = f"USUARIO:{author}" if author else None
    b = f"MARCA:{brand}" if brand else None
    pl = f"PLATAFORMA:{platform}" if platform else None

    if b:
        _bump_node(delta.nodes, b, "MARCA", brand, sentiment, score)
    if u:
        _bump_node(delta.nodes, u, "USUARIO", author, sentiment, score)
    if pl:
        _bump_node(delta.nodes, pl, "PLATAFORMA", platform, sentiment, score)
    for h in hashtags:
        _bump_node(delta.nodes, f"HASHTAG:{h}", "HASHTAG", h, sentiment, score)
    for k in keywords:
        _bump_node(delta.nodes, f"PALABRA:{k}", "PALABRA", k, sentiment, score)

    if u and b:
        _bump_edge(delta.edges, u, b, "MENCIONA", score)
    if u and pl:
        _bump_edge(delta.edges, u, pl, "PUBLICA", score)
    if b and pl:
        _bump_edge(delta.edges, b, pl, "EN_PLATAFORMA", score)
    for h in hashtags:
        ht = f"HASHTAG:{h}"
        if u:
            _bump_edge(delta.edges, u, ht, "ETIQUETA", score)
        if b:
            _bump_edge(delta.edges, b, ht, "CON_HASHTAG", score)
    for k in keywords:
        pw = f"PALABRA:{k}"
        if b:
            _bump_edge(delta.edges, pw, b, "APARECE_EN", score)
        if u:
            _bump_edge(delta.edges, pw, u, "USA", score)


def refresh_buckets(dsn: str, window_minutes: int = 20) -> None:
    """Actualiza la serie temporal de sentimiento por minuto en Postgres."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(BUCKETS_SQL, {"window": window_minutes})
        conn.commit()
    finally:
        conn.close()


def seed_graph(graph_limit: int, neo4j_cfg=None) -> int:
    """Siembra inicial: reconstruye el grafo en Neo4j desde el historico."""
    from ..graph import neo4j_sink

    if neo4j_cfg is not None:
        uri, user, pwd = neo4j_cfg
        return neo4j_sink.seed_graph(graph_limit, neo4j_cfg=(uri, user, pwd))
    return neo4j_sink.seed_graph(graph_limit)


def apply_graph(batch_id: int, delta: "GraphDelta", neo4j_cfg=None) -> bool:
    """Aplica el delta del micro-lote al grafo en Neo4j (idempotente)."""
    from ..graph import neo4j_sink

    if neo4j_cfg is not None:
        uri, user, pwd = neo4j_cfg
        return neo4j_sink.apply_delta(
            batch_id, delta.nodes, delta.edges, neo4j_cfg=(uri, user, pwd)
        )
    return neo4j_sink.apply_delta(batch_id, delta.nodes, delta.edges)



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
    return settings.database.dsn()
