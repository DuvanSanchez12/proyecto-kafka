"""
Constructor del grafo de co-ocurrencia (marca / usuario / hashtag / palabra /
plataforma) estilo Neo4j, expresado como SQL.

Decision de diseno: el grafo es una **vista derivada** de la tabla ``mentions``.
En cada micro-lote se recalcula completo y se reemplaza dentro de una sola
transaccion. Esto lo hace idempotente (un reintento de Spark no duplica aristas)
y siempre consistente con los hechos. El costo es O(filas de mentions) por
lote; para el volumen de una demo es despreciable y, si creciera, la misma
consulta se convierte en un REFRESH MATERIALIZED VIEW incremental.
"""

from __future__ import annotations

CONTRIBUTIONS = """
SELECT m.brand,
       'MARCA:'   || m.brand      AS node_id,
       'MARCA'                    AS label,
       m.brand                    AS name,
       m.sentiment,
       m.score
FROM mentions m
UNION ALL
SELECT m.brand, 'USUARIO:' || m.author, 'USUARIO', m.author, m.sentiment, m.score
FROM mentions m
UNION ALL
SELECT m.brand, 'PLATAFORMA:' || m.platform, 'PLATAFORMA', m.platform, m.sentiment, m.score
FROM mentions m
UNION ALL
SELECT m.brand, 'HASHTAG:' || h, 'HASHTAG', h, m.sentiment, m.score
FROM mentions m, LATERAL unnest(m.hashtags) AS h
UNION ALL
SELECT m.brand, 'PALABRA:' || k, 'PALABRA', k, m.sentiment, m.score
FROM mentions m, LATERAL unnest(m.keywords) AS k
"""

NODES_SQL = f"""
WITH contrib AS (
    {CONTRIBUTIONS}
),
agg AS (
    SELECT node_id,
           label,
           name,
           COUNT(*)                                        AS weight,
           COUNT(*) FILTER (WHERE sentiment = 'POSITIVO')  AS pos_count,
           COUNT(*) FILTER (WHERE sentiment = 'NEUTRAL')   AS neu_count,
           COUNT(*) FILTER (WHERE sentiment = 'NEGATIVO')  AS neg_count,
           AVG(score)                                      AS avg_score
    FROM contrib
    GROUP BY node_id, label, name
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY label ORDER BY weight DESC, ABS(avg_score) DESC) AS rn
    FROM agg
),
kept AS (
    SELECT * FROM ranked
    WHERE label IN ('MARCA', 'PLATAFORMA') OR rn <= %(limit)s
)
INSERT INTO graph_nodes
    (node_id, label, name, weight, pos_count, neu_count, neg_count, sentiment, mentions)
SELECT node_id,
       label,
       name,
       weight,
       pos_count,
       neu_count,
       neg_count,
       CASE
           WHEN avg_score >  0.06 THEN 'POSITIVO'
           WHEN avg_score < -0.06 THEN 'NEGATIVO'
           ELSE 'NEUTRAL'
       END,
       weight
FROM kept
ON CONFLICT (node_id) DO UPDATE SET
    label     = EXCLUDED.label,
    name      = EXCLUDED.name,
    weight    = EXCLUDED.weight,
    pos_count = EXCLUDED.pos_count,
    neu_count = EXCLUDED.neu_count,
    neg_count = EXCLUDED.neg_count,
    sentiment = EXCLUDED.sentiment,
    mentions  = EXCLUDED.mentions
"""

EDGES_SQL = """
WITH pairs AS (
    SELECT m.mention_id,
           m.sentiment,
           m.score,
           'USUARIO:'    || m.author   AS u,
           'MARCA:'      || m.brand    AS b,
           'PLATAFORMA:' || m.platform AS pl,
           CASE WHEN h IS NULL THEN NULL ELSE 'HASHTAG:' || h END AS ht,
           CASE WHEN k IS NULL THEN NULL ELSE 'PALABRA:' || k END AS pw
    FROM mentions m
    LEFT JOIN LATERAL unnest(m.hashtags) AS h ON TRUE
    LEFT JOIN LATERAL unnest(m.keywords) AS k ON TRUE
),
raw_edges AS (
    SELECT u  AS src, b  AS dst, 'MENCIONA'   AS rel, sentiment, score FROM pairs WHERE u  IS NOT NULL AND b  IS NOT NULL
    UNION ALL
    SELECT u,  pl, 'PUBLICA',    sentiment, score FROM pairs WHERE u  IS NOT NULL AND pl IS NOT NULL
    UNION ALL
    SELECT u,  ht, 'ETIQUETA',   sentiment, score FROM pairs WHERE ht IS NOT NULL
    UNION ALL
    SELECT pw, b,  'APARECE_EN', sentiment, score FROM pairs WHERE pw IS NOT NULL
    UNION ALL
    SELECT pw, u,  'USA',        sentiment, score FROM pairs WHERE pw IS NOT NULL
    UNION ALL
    SELECT b,  ht, 'CON_HASHTAG',    sentiment, score FROM pairs WHERE ht IS NOT NULL
    UNION ALL
    SELECT b,  pl, 'EN_PLATAFORMA',  sentiment, score FROM pairs WHERE pl IS NOT NULL
),
agg AS (
    SELECT src,
           dst,
           rel,
           COUNT(*)   AS weight,
           AVG(score) AS avg_score
    FROM raw_edges
    GROUP BY src, dst, rel
)
INSERT INTO graph_edges (edge_id, src, dst, rel, weight, sentiment)
SELECT src || '->' || dst || ':' || rel, src, dst, rel, weight,
       CASE
           WHEN avg_score >  0.06 THEN 'POSITIVO'
           WHEN avg_score < -0.06 THEN 'NEGATIVO'
           ELSE 'NEUTRAL'
       END
FROM agg e
WHERE EXISTS (SELECT 1 FROM graph_nodes n WHERE n.node_id = e.src)
  AND EXISTS (SELECT 1 FROM graph_nodes n WHERE n.node_id = e.dst)
ON CONFLICT (edge_id) DO UPDATE SET
    weight    = EXCLUDED.weight,
    sentiment = EXCLUDED.sentiment
"""


def refresh_sql() -> list[tuple[str, str]]:
    """Sentencias, en orden, para reconstruir la instantanea del grafo."""
    return [
        ("limpiar aristas", "DELETE FROM graph_edges"),
        ("limpiar nodos", "DELETE FROM graph_nodes"),
        ("insertar nodos", NODES_SQL),
        ("insertar aristas", EDGES_SQL),
    ]


# ---------------------------------------------------------------------------
# Serie temporal de sentimiento por minuto (idempotente)
# ---------------------------------------------------------------------------
BUCKETS_SQL = """
INSERT INTO sentiment_buckets (bucket, sentiment, mentions)
SELECT date_trunc('minute', ts) AS bucket,
       sentiment,
       COUNT(*) AS mentions
FROM mentions
WHERE ts > now() - make_interval(mins => %(window)s)
GROUP BY 1, 2
ON CONFLICT (bucket, sentiment) DO UPDATE SET mentions = EXCLUDED.mentions
"""
