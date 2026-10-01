import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Sondea un endpoint cada `intervalMs`. Devuelve el ultimo dato valido y el
 * ultimo error; en un dashboard en vivo interesa seguir mostrando el dato
 * anterior cuando una lectura falla, por eso no se limpia `data`.
 */
export function usePolling(fetcher, intervalMs, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const latest = useRef(fetcher);
  latest.current = fetcher;

  useEffect(() => {
    let alive = true;
    let timer = null;

    const tick = async () => {
      try {
        const value = await latest.current();
        if (alive) {
          setData(value);
          setError(null);
        }
      } catch (err) {
        if (alive) setError(err);
      } finally {
        if (alive) timer = setTimeout(tick, intervalMs);
      }
    };

    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);

  return { data, error };
}

const VALID = new Set(["POSITIVO", "NEUTRAL", "NEGATIVO"]);
const pickSentiment = (value) => (VALID.has(value) ? value : "NEUTRAL");
const majority = (counts) => {
  const [pos, neu, neg] = counts;
  if (pos >= neu && pos >= neg) return "POSITIVO";
  if (neg >= neu) return "NEGATIVO";
  return "NEUTRAL";
};

/**
 * Construye en el navegador un grafo que crece durante la sesion: cada mensaje
 * nuevo del feed (deduplicado por mention_id) agrega/refuerza nodos y aristas.
 * No persiste nada: al recargar la pestana se empieza de cero. Se apoya en el
 * mismo modelo de relaciones del grafo global (marca, usuario, plataforma,
 * palabra) para que ambos se lean igual, pero sin hashtags porque el feed no
 * los trae.
 */
export function useSessionGraph(messages, brand = "Marca", maxNodes = 160) {
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const nodes = useRef(new Map());
  const edges = useRef(new Map());
  const seen = useRef(new Set());

  const reset = useCallback(() => {
    nodes.current = new Map();
    edges.current = new Map();
    seen.current = new Set();
    setGraph({ nodes: [], edges: [] });
  }, []);

  useEffect(() => {
    const batch = Array.isArray(messages) ? messages : [];
    if (batch.length === 0) return;
    let changed = false;

    const touchNode = (id, label, name, sentiment) => {
      let n = nodes.current.get(id);
      if (n) nodes.current.delete(id);
      else n = { node_id: id, label, name, weight: 0, pos: 0, neu: 0, neg: 0 };
      n.name = name;
      n.weight += 1;
      const s = pickSentiment(sentiment);
      n[s === "POSITIVO" ? "pos" : s === "NEGATIVO" ? "neg" : "neu"] += 1;
      nodes.current.set(id, n);
    };

    const touchEdge = (src, dst, rel, sentiment) => {
      const id = `${src}->${dst}:${rel}`;
      let e = edges.current.get(id);
      if (e) edges.current.delete(id);
      else e = { edge_id: id, src, dst, rel, weight: 0, pos: 0, neu: 0, neg: 0 };
      e.weight += 1;
      const s = pickSentiment(sentiment);
      e[s === "POSITIVO" ? "pos" : s === "NEGATIVO" ? "neg" : "neu"] += 1;
      edges.current.set(id, e);
    };

    for (const m of batch) {
      if (!m || !m.mention_id || seen.current.has(m.mention_id)) continue;
      seen.current.add(m.mention_id);
      changed = true;

      const s = m.sentiment;
      const brandId = "MARCA";
      const userId = `USUARIO:${m.author}`;
      touchNode(brandId, "MARCA", brand, s);
      touchNode(userId, "USUARIO", m.author, s);
      touchEdge(userId, brandId, "MENCIONA", s);

      if (m.platform) {
        const pid = `PLATAFORMA:${m.platform}`;
        touchNode(pid, "PLATAFORMA", m.platform, s);
        touchEdge(userId, pid, "PUBLICA", s);
        touchEdge(brandId, pid, "EN_PLATAFORMA", s);
      }

      for (const k of m.keywords ?? []) {
        const kid = `PALABRA:${k}`;
        touchNode(kid, "PALABRA", k, s);
        touchEdge(kid, brandId, "APARECE_EN", s);
      }
    }

    if (!changed) return;

    if (nodes.current.size > maxNodes) {
      for (const id of Array.from(nodes.current.keys())) {
        if (nodes.current.size <= maxNodes) break;
        if (id === "MARCA") continue;
        nodes.current.delete(id);
      }
    }
    for (const [id, e] of Array.from(edges.current.entries())) {
      if (!nodes.current.has(e.src) || !nodes.current.has(e.dst)) edges.current.delete(id);
    }

    const asArray = (map, counts) =>
      Array.from(map.values()).map((item) => ({
        ...item,
        sentiment: majority(counts(item)),
        pos_count: item.pos,
        neu_count: item.neu,
        neg_count: item.neg,
      }));

    setGraph({
      nodes: asArray(nodes.current, (n) => [n.pos, n.neu, n.neg]),
      edges: asArray(edges.current, (e) => [e.pos, e.neu, e.neg]),
    });
  }, [messages, brand, maxNodes]);

  return { graph, reset };
}
