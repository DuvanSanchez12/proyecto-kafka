from __future__ import annotations

import os
from typing import Any, Dict, List

from neo4j import GraphDatabase


def get_cfg():
    uri = os.getenv("NEO4J_URI", "neo4j://neo4j:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "brandpulse123")
    return uri, user, pwd


def fetch_graph(limit: int = 140) -> Dict[str, Any]:
    uri, user, pwd = get_cfg()
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    try:
        with driver.session() as session:
            # get nodes (top by weight overall, keeping MARCA/PLATAFORMA prominent)
            res = session.run(
                """
                MATCH (n)
                WHERE NOT n:Batch
                WITH n, COALESCE(n.weight, 0) AS w
                RETURN n.id AS node_id, labels(n) AS labels, n.label AS label, n.name AS name,
                       COALESCE(n.weight, 0) AS weight,
                       COALESCE(n.pos_count, 0) AS pos_count,
                       COALESCE(n.neu_count, 0) AS neu_count,
                       COALESCE(n.neg_count, 0) AS neg_count,
                       COALESCE(n.sentiment, 'NEUTRAL') AS sentiment
                ORDER BY CASE WHEN 'MARCA' IN labels(n) THEN 1000000 ELSE 0 END + w DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            for r in res:
                labels_list = r["labels"] or []
                # prefer explicit label field
                lbl = r["label"] or (labels_list[0] if labels_list else "NODO")
                nodes.append(
                    {
                        "node_id": r["node_id"],
                        "label": lbl,
                        "name": r["name"],
                        "weight": r["weight"],
                        "pos_count": r["pos_count"],
                        "neu_count": r["neu_count"],
                        "neg_count": r["neg_count"],
                        "sentiment": r["sentiment"],
                    }
                )
            ids = [n["node_id"] for n in nodes]
            if ids:
                res2 = session.run(
                    """
                    MATCH (a)-[r:REL]->(b)
                    WHERE a.id IN $ids AND b.id IN $ids
                    RETURN COALESCE(r.src, a.id) AS src, COALESCE(r.dst, b.id) AS dst,
                           COALESCE(r.rel, type(r)) AS rel,
                           COALESCE(r.weight, 0) AS weight,
                           COALESCE(r.sentiment, 'NEUTRAL') AS sentiment
                    ORDER BY weight DESC
                    """,
                    ids=ids,
                )
                seen = set()
                for r in res2:
                    key = (r["src"], r["dst"], r["rel"])
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(
                        {
                            "edge_id": f"{r['src']}->{r['dst']}:{r['rel']}",
                            "src": r["src"],
                            "dst": r["dst"],
                            "rel": r["rel"],
                            "weight": r["weight"],
                            "sentiment": r["sentiment"],
                        }
                    )
    finally:
        driver.close()
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}
