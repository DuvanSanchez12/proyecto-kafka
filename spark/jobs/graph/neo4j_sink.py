"""
Sumidero del grafo de co-ocurrencia en Neo4j.

Dos modos, ambos transaccionales:

* ``seed_graph``     : reconstruye el grafo desde cero a partir de la
                       instantanea agregada de ``mentions`` (se usa una sola
                       vez, al arrancar el job, para no perder el historico).
* ``apply_delta``    : aplica **incrementos** por micro-lote. Cada arista y
                       nodo que aparece en el lote suma su peso; el grafo
                       crece en vivo sin borrar lo anterior.

Idempotencia
------------
Spark puede reintentar un micro-lote. Para no contar dos veces el mismo lote,
``apply_delta`` deja un nodo marcador ``(:Batch {id})`` y, si ya existe, no hace
nada. El marcador y los incrementos se escriben en la **misma transaccion**, asi
que un reintento nunca duplica pesos. ``seed_graph`` borra los nodos del grafo
pero **conserva** los marcadores de lote, de modo que un reinicio no vuelve a
contar lotes ya aplicados.
"""

from __future__ import annotations

import os

import psycopg2
from neo4j import GraphDatabase
from psycopg2.extras import RealDictCursor

# Etiquetas internas que no forman parte del grafo visible.
_INTERNAL_LABELS = {"Batch"}

# Umbral de sentimiento (igual que el usado por el resto del proyecto).
_POS_THRESHOLD = 0.06
_NEG_THRESHOLD = -0.06

_SENTIMENT_CASE = (
    "CASE WHEN {sum} / {weight} > 0.06 THEN 'POSITIVO' "
    "WHEN {sum} / {weight} < -0.06 THEN 'NEGATIVO' "
    "ELSE 'NEUTRAL' END"
)


def get_neo4j_cfg():
    uri = os.getenv("NEO4J_URI", "neo4j://neo4j:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "brandpulse123")
    return uri, user, pwd


def _driver(cfg):
    uri, user, pwd = cfg or get_neo4j_cfg()
    return GraphDatabase.driver(uri, auth=(user, pwd))


def _dsn() -> str:
    dsn = os.getenv("POSTGRES_DSN") or None
    if dsn:
        return dsn
    return (
        f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'brandpulse')} "
        f"user={os.getenv('POSTGRES_USER', 'marketing')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'marketing')}"
    )


# ---------------------------------------------------------------------------
# Instantanea agregada desde Postgres (para la siembra inicial)
# ---------------------------------------------------------------------------
NODES_SNAPSHOT_SQL = """
WITH contrib AS (
    SELECT m.brand, 'MARCA:'||m.brand AS node_id, 'MARCA' AS label, m.brand AS name, m.sentiment, m.score FROM mentions m
    UNION ALL
    SELECT m.brand, 'USUARIO:'||m.author, 'USUARIO', m.author, m.sentiment, m.score FROM mentions m
    UNION ALL
    SELECT m.brand, 'PLATAFORMA:'||m.platform, 'PLATAFORMA', m.platform, m.sentiment, m.score FROM mentions m
    UNION ALL
    SELECT m.brand, 'HASHTAG:'||h, 'HASHTAG', h, m.sentiment, m.score FROM mentions m, LATERAL unnest(m.hashtags) AS h
    UNION ALL
    SELECT m.brand, 'PALABRA:'||k, 'PALABRA', k, m.sentiment, m.score FROM mentions m, LATERAL unnest(m.keywords) AS k
),
agg AS (
    SELECT node_id, label, name,
           COUNT(*) AS weight,
           COUNT(*) FILTER (WHERE sentiment = 'POSITIVO') AS pos,
           COUNT(*) FILTER (WHERE sentiment = 'NEUTRAL')  AS neu,
           COUNT(*) FILTER (WHERE sentiment = 'NEGATIVO') AS neg,
           SUM(score) AS score_sum
    FROM contrib
    GROUP BY node_id, label, name
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY label ORDER BY weight DESC, ABS(score_sum) / weight DESC
    ) AS rn
    FROM agg
),
kept AS (
    SELECT * FROM ranked
    WHERE label IN ('MARCA', 'PLATAFORMA') OR rn <= %s
)
SELECT node_id, label, name, weight, pos, neu, neg, score_sum
FROM kept
"""

EDGES_SNAPSHOT_SQL = """
WITH base AS (
    SELECT m.mention_id, m.sentiment, m.score,
           'USUARIO:'||m.author AS u,
           'MARCA:'||m.brand AS b,
           'PLATAFORMA:'||m.platform AS pl
    FROM mentions m
),
ht AS (
    SELECT m.mention_id, 'HASHTAG:'||h AS ht
    FROM mentions m, LATERAL unnest(m.hashtags) AS h
),
kw AS (
    SELECT m.mention_id, 'PALABRA:'||k AS pw
    FROM mentions m, LATERAL unnest(m.keywords) AS k
),
raw AS (
    SELECT u AS src, b AS dst, 'MENCIONA' AS rel, sentiment, score
    FROM base WHERE u IS NOT NULL AND b IS NOT NULL
    UNION ALL
    SELECT u, pl, 'PUBLICA', sentiment, score
    FROM base WHERE u IS NOT NULL AND pl IS NOT NULL
    UNION ALL
    SELECT u, ht, 'ETIQUETA', sentiment, score
    FROM base JOIN ht USING (mention_id) WHERE u IS NOT NULL
    UNION ALL
    SELECT pw, b, 'APARECE_EN', sentiment, score
    FROM base JOIN kw USING (mention_id) WHERE b IS NOT NULL
    UNION ALL
    SELECT pw, u, 'USA', sentiment, score
    FROM base JOIN kw USING (mention_id) WHERE u IS NOT NULL
    UNION ALL
    SELECT b, ht, 'CON_HASHTAG', sentiment, score
    FROM base JOIN ht USING (mention_id) WHERE b IS NOT NULL
    UNION ALL
    SELECT b, pl, 'EN_PLATAFORMA', sentiment, score
    FROM base WHERE b IS NOT NULL AND pl IS NOT NULL
),
agg AS (
    SELECT src, dst, rel, COUNT(*) AS weight, SUM(score) AS score_sum
    FROM raw
    GROUP BY src, dst, rel
)
SELECT src, dst, rel, weight, score_sum
FROM agg
"""


def fetch_snapshot(graph_limit: int) -> tuple[list[dict], list[dict]]:
    conn = psycopg2.connect(_dsn())
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(NODES_SNAPSHOT_SQL, (graph_limit,))
            nodes = [dict(r) for r in cur.fetchall()]
            cur.execute(EDGES_SNAPSHOT_SQL)
            edges = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    node_ids = {n["node_id"] for n in nodes}
    edges = [e for e in edges if e["src"] in node_ids and e["dst"] in node_ids]
    return nodes, edges


# ---------------------------------------------------------------------------
# Siembra: reconstruye el grafo desde la instantanea (una sola vez)
# ---------------------------------------------------------------------------
def seed_graph(graph_limit: int, neo4j_cfg=None) -> int:
    nodes, edges = fetch_snapshot(graph_limit)
    driver = _driver(neo4j_cfg)
    try:
        with driver.session() as session:
            session.execute_write(_seed_tx, nodes, edges)
    finally:
        driver.close()
    return len(nodes)


def _seed_tx(tx, nodes, edges):
    # Conserva los marcadores (:Batch): permiten no recontrar lotes ya aplicados
    # tras un reinicio del job.
    tx.run("MATCH (n) WHERE NOT n:Batch DETACH DELETE n")

    for label, subset in _group_by_label(nodes):
        tx.run(
            f"UNWIND $rows AS n "
            f"MERGE (x:`{label}` {{id: n.node_id}}) "
            "SET x.label = n.label, x.name = n.name, x.weight = n.weight, "
            "x.pos_count = n.pos, x.neu_count = n.neu, x.neg_count = n.neg, "
            "x.score_sum = n.score_sum "
            "SET x.sentiment = "
            + _SENTIMENT_CASE.format(sum="x.score_sum", weight="x.weight"),
            rows=subset,
        )

    if edges:
        tx.run(
            "UNWIND $rows AS e "
            "MATCH (s {id: e.src}) "
            "MATCH (d {id: e.dst}) "
            "MERGE (s)-[r:REL {rel: e.rel, src: e.src, dst: e.dst}]->(d) "
            "SET r.weight = e.weight, r.score_sum = e.score_sum "
            "SET r.sentiment = "
            + _SENTIMENT_CASE.format(sum="r.score_sum", weight="r.weight"),
            rows=edges,
        )


# ---------------------------------------------------------------------------
# Incremento: aplica el delta de un micro-lote (idempotente por batch)
# ---------------------------------------------------------------------------
def apply_delta(batch_id: int, nodes: dict, edges: dict, neo4j_cfg=None) -> bool:
    """Suma los nodos/aristas del lote. Devuelve True si aplico el lote."""
    driver = _driver(neo4j_cfg)
    try:
        with driver.session() as session:
            return session.execute_write(
                _apply_delta_tx,
                int(batch_id),
                list(nodes.values()),
                list(edges.values()),
            )
    finally:
        driver.close()


def _apply_delta_tx(tx, batch_id, nodes, edges):
    already = tx.run(
        "MATCH (b:Batch {id: $id}) RETURN b.id AS id", id=batch_id
    ).single()
    if already is not None:
        return False

    for label, subset in _group_by_label(nodes):
        tx.run(
            f"UNWIND $rows AS n "
            f"MERGE (x:`{label}` {{id: n.node_id}}) "
            "ON CREATE SET x.label = n.label, x.name = n.name, "
            "x.weight = 0, x.pos_count = 0, x.neu_count = 0, x.neg_count = 0, "
            "x.score_sum = 0.0 "
            "SET x.weight = x.weight + n.weight, "
            "    x.pos_count = x.pos_count + n.pos, "
            "    x.neu_count = x.neu_count + n.neu, "
            "    x.neg_count = x.neg_count + n.neg, "
            "    x.score_sum = x.score_sum + n.score_sum "
            "SET x.sentiment = "
            + _SENTIMENT_CASE.format(sum="x.score_sum", weight="x.weight"),
            rows=subset,
        )

    if edges:
        tx.run(
            "UNWIND $rows AS e "
            "MATCH (s {id: e.src}) "
            "MATCH (d {id: e.dst}) "
            "MERGE (s)-[r:REL {rel: e.rel, src: e.src, dst: e.dst}]->(d) "
            "ON CREATE SET r.weight = 0, r.score_sum = 0.0 "
            "SET r.weight = r.weight + e.weight, "
            "    r.score_sum = r.score_sum + e.score_sum "
            "SET r.sentiment = "
            + _SENTIMENT_CASE.format(sum="r.score_sum", weight="r.weight"),
            rows=edges,
        )

    tx.run("MERGE (b:Batch {id: $id})", id=batch_id)
    return True


def _group_by_label(nodes):
    labels = sorted({n["label"] for n in nodes})
    return [(label, [n for n in nodes if n["label"] == label]) for label in labels]
