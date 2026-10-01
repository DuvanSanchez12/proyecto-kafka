"""
API REST que alimenta el dashboard de BrandPulse.

Es una capa de solo lectura sobre Postgres: el trabajo pesado (clasificar,
agregar, armar el grafo) ya lo hizo Spark. Aqui solo se sirven las consultas
que el frontend necesita, con columnas ya normalizadas a JSON.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db

BRAND = os.getenv("BRAND", "Nike")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_pool()
    yield


app = FastAPI(title="BrandPulse API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    state = db.query_one("SELECT brand, last_batch, last_updated FROM pipeline_state WHERE id = 1")
    alive = db.query_one("SELECT COUNT(*) AS n FROM mentions")
    return {
        "status": "ok",
        "brand": state["brand"] if state else BRAND,
        "last_batch": state["last_batch"] if state else -1,
        "last_updated": state["last_updated"].isoformat() if state and state["last_updated"] else None,
        "mentions": alive["n"] if alive else 0,
    }


@app.get("/api/kpis")
def kpis() -> dict:
    row = db.query_one(
        """
        SELECT total, positivos, neutrales, negativos, etiquetados, correctos,
               score_promedio, confianza_promedio, comparaciones_promedio,
               autores, plataformas
        FROM v_kpis
        """
    ) or {}
    total = row.get("total") or 0
    etiquetados = row.get("etiquetados") or 0
    correctos = row.get("correctos") or 0
    row["exactitud"] = round(100.0 * correctos / etiquetados, 2) if etiquetados else 0.0
    row["pct_positivo"] = round(100.0 * (row.get("positivos") or 0) / total, 1) if total else 0.0
    row["pct_neutral"] = round(100.0 * (row.get("neutrales") or 0) / total, 1) if total else 0.0
    row["pct_negativo"] = round(100.0 * (row.get("negativos") or 0) / total, 1) if total else 0.0
    return row


@app.get("/api/trend")
def trend(minutes: int = Query(30, ge=1, le=1440)) -> dict:
    rows = db.query(
        """
        SELECT bucket, sentiment, mentions
        FROM sentiment_buckets
        WHERE bucket >= date_trunc('minute', now()) - make_interval(mins => %s)
        ORDER BY bucket
        """,
        (minutes,),
    )
    series: dict[str, dict] = {}
    for row in rows:
        key = row["bucket"].isoformat()
        slot = series.setdefault(
            key, {"bucket": key, "POSITIVO": 0, "NEUTRAL": 0, "NEGATIVO": 0}
        )
        slot[row["sentiment"]] = row["mentions"]
    ordered = [series[k] for k in sorted(series)]
    for slot in ordered:
        slot["total"] = slot["POSITIVO"] + slot["NEUTRAL"] + slot["NEGATIVO"]
    return {"minutes": minutes, "points": ordered}


@app.get("/api/graph")
def graph(limit: int = Query(140, ge=10, le=1000)) -> dict:
    nodes = db.query(
        """
        SELECT node_id, label, name, weight, pos_count, neu_count, neg_count, sentiment
        FROM graph_nodes
        ORDER BY (label = 'MARCA') DESC, weight DESC
        LIMIT %s
        """,
        (limit,),
    )
    ids = [n["node_id"] for n in nodes]
    edges = db.query(
        """
        SELECT edge_id, src, dst, rel, weight, sentiment
        FROM graph_edges
        WHERE src = ANY(%s) AND dst = ANY(%s)
        ORDER BY weight DESC
        """,
        (ids, ids),
    )
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


@app.get("/api/messages")
def messages(limit: int = Query(30, ge=1, le=200)) -> dict:
    rows = db.query(
        """
        SELECT mention_id, ts, platform, author, text, sentiment, score, confidence,
               keywords, expected, (expected = sentiment) AS correct,
               dnc_comparisons, sort_comparisons, dnc_levels
        FROM mentions
        ORDER BY processed_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    for row in rows:
        if row["ts"] is not None:
            row["ts"] = row["ts"].isoformat()
    return {"messages": rows}


@app.get("/api/accuracy")
def accuracy() -> dict:
    matrix = db.query(
        """
        SELECT COALESCE(expected, 'SIN_ETIQUETA') AS esperado,
               sentiment AS predicho,
               COUNT(*) AS total
        FROM mentions
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    )
    by_label = db.query(
        """
        SELECT expected AS clase,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE expected = sentiment) AS correctos,
               ROUND(100.0 * COUNT(*) FILTER (WHERE expected = sentiment) / COUNT(*), 2) AS exactitud
        FROM mentions
        WHERE expected IS NOT NULL
        GROUP BY expected
        ORDER BY expected
        """
    )
    return {"matriz": matrix, "por_clase": by_label}


@app.get("/api/complexity")
def complexity(limit: int = Query(40, ge=1, le=500)) -> dict:
    batches = db.query(
        """
        SELECT batch_index, processed_at, messages, total_tokens,
               dnc_comparisons, dnc_levels, sort_comparisons,
               theoretical_min, merge_operations
        FROM complexity_stats
        ORDER BY batch_index DESC
        LIMIT %s
        """,
        (limit,),
    )
    for row in batches:
        if row["processed_at"] is not None:
            row["processed_at"] = row["processed_at"].isoformat()
    total = db.query_one(
        """
        SELECT COALESCE(SUM(messages), 0)          AS mensajes,
               COALESCE(SUM(total_tokens), 0)      AS tokens,
               COALESCE(SUM(dnc_comparisons), 0)   AS comparaciones_reales,
               COALESCE(SUM(theoretical_min), 0)   AS comparaciones_teoricas,
               COALESCE(SUM(merge_operations), 0)  AS mezclas,
               COALESCE(MAX(dnc_levels), 0)        AS niveles
        FROM complexity_stats
        """
    ) or {}
    return {"batches": batches, "total": total}
