import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { LABEL_COLOR, LABEL_TEXT, SENTIMENT } from "../theme";

const REL_TEXT = {
  MENCIONA: "menciona",
  PUBLICA: "publica en",
  ETIQUETA: "etiqueta",
  APARECE_EN: "aparece en",
  USA: "usa",
  CON_HASHTAG: "con hashtag",
  EN_PLATAFORMA: "en plataforma",
};

const KIND_ORDER = ["MARCA", "PLATAFORMA", "HASHTAG", "PALABRA", "USUARIO"];
const KIND_LEVEL = { MARCA: 100, PLATAFORMA: 72, HASHTAG: 52, PALABRA: 32, USUARIO: 12 };
const TOP_OPTIONS = [15, 30, 60, 120];

const STYLE = [
  {
    selector: "node",
    style: {
      "background-color": "#334155",
      label: "data(label)",
      color: "#e2e8f0",
      "font-size": 9,
      "text-wrap": "ellipsis",
      "text-max-width": 86,
      "text-valign": "bottom",
      "text-margin-y": 3,
      "text-outline-color": "#020617",
      "text-outline-width": 2,
      width: "mapData(size, 0, 1, 14, 58)",
      height: "mapData(size, 0, 1, 14, 58)",
      "border-width": 3,
      "border-color": "#0b1120",
      "transition-property": "opacity, border-width, border-color",
      "transition-duration": "160ms",
    },
  },
  {
    selector: "edge",
    style: {
      width: "mapData(ew, 0, 1, 0.6, 3.2)",
      "line-color": "#2b3a55",
      "target-arrow-color": "#2b3a55",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.7,
      opacity: 0.26,
      label: "data(relText)",
      "font-size": 7,
      color: "#94a3b8",
      "text-outline-color": "#020617",
      "text-outline-width": 3,
      "text-opacity": 0,
      "transition-property": "opacity, text-opacity",
      "transition-duration": "160ms",
    },
  },
  {
    selector: 'node[kind = "MARCA"]',
    style: { "background-color": LABEL_COLOR.MARCA, "font-size": 13, "font-weight": "bold" },
  },
  { selector: 'node[kind = "PLATAFORMA"]', style: { "background-color": LABEL_COLOR.PLATAFORMA, "font-size": 10 } },
  { selector: 'node[kind = "HASHTAG"]', style: { "background-color": LABEL_COLOR.HASHTAG } },
  { selector: 'node[kind = "PALABRA"]', style: { "background-color": LABEL_COLOR.PALABRA } },
  { selector: 'node[kind = "USUARIO"]', style: { "background-color": LABEL_COLOR.USUARIO } },
  { selector: 'node[sentiment = "POSITIVO"]', style: { "border-color": SENTIMENT.POSITIVO.color } },
  { selector: 'node[sentiment = "NEUTRAL"]', style: { "border-color": SENTIMENT.NEUTRAL.color } },
  { selector: 'node[sentiment = "NEGATIVO"]', style: { "border-color": SENTIMENT.NEGATIVO.color } },
  { selector: 'edge[sentiment = "POSITIVO"]', style: { "line-color": "#166534", "target-arrow-color": "#166534" } },
  { selector: 'edge[sentiment = "NEUTRAL"]', style: { "line-color": "#854d0e", "target-arrow-color": "#854d0e" } },
  { selector: 'edge[sentiment = "NEGATIVO"]', style: { "line-color": "#991b1b", "target-arrow-color": "#991b1b" } },
  { selector: "node.dim", style: { opacity: 0.07, "text-opacity": 0 } },
  { selector: "edge.dim", style: { opacity: 0.03, "text-opacity": 0 } },
  {
    selector: "node.focus",
    style: { opacity: 1, "text-opacity": 1, "z-index": 30, "font-size": 11, "border-width": 5 },
  },
  {
    selector: "edge.focus",
    style: { opacity: 0.95, "text-opacity": 1, "z-index": 20, width: "mapData(ew, 0, 1, 1.4, 4.8)" },
  },
  { selector: ":selected", style: { "border-color": "#f8fafc" } },
];

const LAYOUT = {
  name: "concentric",
  animate: false,
  padding: 36,
  minNodeSpacing: 22,
  avoidOverlap: true,
  nodeDimensionsIncludeLabels: false,
  startAngle: (3 / 2) * Math.PI,
  clockwise: true,
  concentric: (node) => KIND_LEVEL[node.data("kind")] ?? 5,
  levelWidth: () => 1,
};

export default function GraphView({ graph }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const idsRef = useRef("");
  const [selected, setSelected] = useState(null);
  const [kinds, setKinds] = useState({
    MARCA: true,
    PLATAFORMA: true,
    HASHTAG: true,
    PALABRA: true,
    USUARIO: false,
  });
  const [topN, setTopN] = useState(30);

  const clearFocus = useCallback(() => {
    cyRef.current?.elements().removeClass("dim focus");
  }, []);

  useEffect(() => {
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: STYLE,
      layout: { name: "preset" },
      wheelSensitivity: 0.2,
      minZoom: 0.15,
      maxZoom: 3,
    });
    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      cy.elements().removeClass("dim focus");
      const hood = node.closedNeighborhood();
      cy.elements().difference(hood).addClass("dim");
      hood.addClass("focus");
      setSelected({ ...node.data() });
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        clearFocus();
        setSelected(null);
      }
    });
    cyRef.current = cy;
    return () => cy.destroy();
  }, [clearFocus]);

  const counts = useMemo(() => {
    const acc = {};
    (graph?.nodes ?? []).forEach((n) => {
      acc[n.label] = (acc[n.label] || 0) + 1;
    });
    return acc;
  }, [graph]);

  const visible = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    const byKind = graph.nodes.filter((n) => kinds[n.label]);
    const brand = byKind.filter((n) => n.label === "MARCA");
    const rest = byKind
      .filter((n) => n.label !== "MARCA")
      .sort((a, b) => b.weight - a.weight)
      .slice(0, Math.max(0, topN - brand.length));
    const nodes = [...brand, ...rest];
    const ids = new Set(nodes.map((n) => n.node_id));
    const edges = graph.edges.filter((e) => ids.has(e.src) && ids.has(e.dst));
    return { nodes, edges };
  }, [graph, kinds, topN]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const wanted = new Set(visible.nodes.map((n) => n.node_id));
    const edgeById = new Map(visible.edges.map((e) => [e.edge_id, e]));
    let structural = false;

    const logW = (v) => Math.log(Math.max(2, Number(v) || 1));
    const nw = visible.nodes.map((n) => logW(n.weight));
    const nLo = nw.length ? Math.min(...nw) : 0;
    const nHi = nw.length ? Math.max(...nw) : 1;
    const nSize = (n) => (nHi > nLo ? (logW(n.weight) - nLo) / (nHi - nLo) : 0.6);
    const ewLogs = visible.edges.map((e) => logW(e.weight));
    const eLo = ewLogs.length ? Math.min(...ewLogs) : 0;
    const eHi = ewLogs.length ? Math.max(...ewLogs) : 1;
    const eSize = (e) => (eHi > eLo ? (logW(e.weight) - eLo) / (eHi - eLo) : 0.5);

    cy.nodes().forEach((n) => {
      if (!wanted.has(n.id())) {
        n.remove();
        structural = true;
      }
    });

    visible.nodes.forEach((n) => {
      const existing = cy.getElementById(n.node_id);
      if (existing.nonempty()) {
        existing.data({
          weight: n.weight,
          sentiment: n.sentiment,
          pos: n.pos_count,
          neu: n.neu_count,
          neg: n.neg_count,
          size: nSize(n),
        });
      } else {
        cy.add({
          group: "nodes",
          data: {
            id: n.node_id,
            name: n.name,
            label: n.name,
            kind: n.label,
            weight: n.weight,
            sentiment: n.sentiment,
            pos: n.pos_count,
            neu: n.neu_count,
            neg: n.neg_count,
            size: nSize(n),
          },
        });
        structural = true;
      }
    });

    cy.edges().forEach((e) => {
      if (!edgeById.has(e.id())) {
        e.remove();
        structural = true;
      }
    });

    visible.edges.forEach((e) => {
      const relText = REL_TEXT[e.rel] || e.rel;
      const existing = cy.getElementById(e.edge_id);
      if (existing.nonempty()) {
        existing.data({ weight: e.weight, sentiment: e.sentiment, relText, ew: eSize(e) });
      } else if (cy.getElementById(e.src).nonempty() && cy.getElementById(e.dst).nonempty()) {
        cy.add({
          group: "edges",
          data: {
            id: e.edge_id,
            source: e.src,
            target: e.dst,
            rel: e.rel,
            relText,
            weight: e.weight,
            sentiment: e.sentiment,
            ew: eSize(e),
          },
        });
        structural = true;
      }
    });

    if (structural) {
      cy.elements().removeClass("dim focus");
      setSelected((prev) => (prev && !wanted.has(prev.id) ? null : prev));
    }

    const signature = visible.nodes.map((n) => n.node_id).sort().join("|");
    if (structural || signature !== idsRef.current) {
      idsRef.current = signature;
      cy.layout(LAYOUT).run();
    }
  }, [visible]);

  const fit = () => cyRef.current?.fit(undefined, 44);

  const toggle = (kind) =>
    setKinds((prev) => ({ ...prev, [kind]: !prev[kind] }));

  return (
    <div className="panel graph-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <h2 style={{ margin: 0 }}>Grafo de co-ocurrencia</h2>
        <span className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>
          mostrando {visible.nodes.length} de {graph?.node_count ?? 0} · {visible.edges.length} aristas
        </span>
      </div>
      <p className="panel-sub">
        Grafo global de todas las menciones. La marca está al centro y cada anillo es un tipo de entidad;
        usá los filtros para quedarte con lo importante.
      </p>

      <div className="graph-tools">
        {KIND_ORDER.map((kind) => (
          <button
            key={kind}
            className={`chip ${kinds[kind] ? "on" : ""}`}
            onClick={() => toggle(kind)}
            title={kinds[kind] ? "ocultar" : "mostrar"}
          >
            <span className="swatch" style={{ background: LABEL_COLOR[kind] }} />
            {LABEL_TEXT[kind]}
            <span className="mono count">{counts[kind] ?? 0}</span>
          </button>
        ))}
        <label className="topsel">
          nodos
          <select value={topN} onChange={(e) => setTopN(Number(e.target.value))}>
            {TOP_OPTIONS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <button className="ghost" onClick={fit}>
          encuadrar
        </button>
      </div>

      <div className="graph-wrap" ref={containerRef} />

      <div className="legend">
        <span className="item">
          <span className="dotmark marca" /> centro = marca
        </span>
        <span className="item">
          <span className="dotmark anillo" /> cada anillo = un tipo (plataforma → hashtag → palabra → usuario)
        </span>
        <span className="item" style={{ marginLeft: "auto" }}>
          clic en un nodo para aislar su vecindario
        </span>
      </div>

      {selected ? (
        <div
          style={{
            marginTop: 10,
            padding: "10px 12px",
            border: "1px solid #16203a",
            borderRadius: 10,
            background: "#0b1424",
            fontSize: 12.5,
          }}
        >
          <strong style={{ color: LABEL_COLOR[selected.kind] }}>{selected.name}</strong>
          <span style={{ color: "var(--muted)" }}> · {LABEL_TEXT[selected.kind]}</span>
          <div className="msg-foot" style={{ marginTop: 6 }}>
            <span className="pill mono">peso {selected.weight}</span>
            <span className="pill" style={{ color: SENTIMENT[selected.sentiment]?.color }}>
              {SENTIMENT[selected.sentiment]?.label ?? selected.sentiment}
            </span>
            <span className="pill mono">+{selected.pos ?? 0}</span>
            <span className="pill mono">~{selected.neu ?? 0}</span>
            <span className="pill mono">-{selected.neg ?? 0}</span>
            <button className="ghost" style={{ marginLeft: "auto" }} onClick={() => { clearFocus(); setSelected(null); }}>
              quitar foco
            </button>
          </div>
        </div>
      ) : (
        <div className="legend" style={{ marginTop: 10 }}>
          relaciones: {Object.values(REL_TEXT).join(" · ")}
        </div>
      )}
    </div>
  );
}
