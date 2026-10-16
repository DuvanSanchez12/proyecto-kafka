"""
Serie temporal de sentimiento por minuto.

El grafo de co-ocurrencia ya no se materializa en Postgres: se construye y
almacena en Neo4j (ver ``jobs/graph/neo4j_sink.py``). Este modulo conserva
unicamente el SQL de los buckets por minuto, que sigue viviendo en el
warehouse.
"""

from __future__ import annotations

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
