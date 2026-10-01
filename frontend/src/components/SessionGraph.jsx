import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { LABEL_COLOR, LABEL_TEXT, SENTIMENT } from "../theme";

const REL_TEXT = {
  MENCIONA: "menciona",
  PUBLICA: "publica en",
  EN_PLATAFORMA: "en plataforma",
  APARECE_EN: "aparece en",
};

const KIND_ORDER = ["MARCA", "PLATAFORMA", "PALABRA", "USUARIO"];

const STYLE = [
  {
    selector: "node",
    style: {
      "background-color": "#334155",
      label: "data(label)",
      color: "#e2e8f0",
      "font-size": 9,
      "text-wrap": "ellipsis",
      "text-max-width": 84,
      "text-valign": "bottom",
      "text-margin-y": 3,
      "text-outline-color": "#020617",
      "text-outline-width": 2,
      width: "mapData(size, 0, 1, 15, 52)",
      height: "mapData(size, 0, 1, 15, 52)",
      "border-width": 3,
      "border-color": "#0b1120",
      "transition-property": "width, height, opacity, border-width",
      "transition-duration": "350ms",
    },
  },
  {
    selector: "edge",
    style: {
      width: "mapData(ew, 0, 1, 0.6, 3)",
      "line-color": "#2b3a55",
      "target-arrow-color": "#2b3a55",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.7,
      opacity: 0.35,
      label: "data(relText)",
      "font-size": 7,
      color: "#94a3b8",
      "text-outline-color": "#020617",
      "text-outline-width": 3,
      "text-opacity": 0,
      "transition-property": "opacity, text-opacity",
      "transition-duration": "300ms",
    },
  },
  { selector: 'node[kind = "MARCA"]', style: { "background-color": LABEL_COLOR.MARCA, "font-size": 13, "font-weight": "bold" } },
  { selector: 'node[kind = "PLATAFORMA"]', style: { "background-color": LABEL_COLOR.PLATAFORMA } },
  { selector: 'node[kind = "HASHTAG"]', style: { "background-color": LABEL_COLOR.HASHTAG } },
  { selector: 'node[kind = "PALABRA"]', style: { "background-color": LABEL_COLOR.PALABRA } },
  { selector: 'node[kind = "USUARIO"]', style: { "background-color": LABEL_COLOR.USUARIO } },
  { selector: 'node[sentiment = "POSITIVO"]', style: { "border-color": SENTIMENT.POSITIVO.color } },
  { selector: 'node[sentiment = "NEUTRAL"]', style: { "border-color": SENTIMENT.NEUTRAL.color } },
  { selector: 'node[sentiment = "NEGATIVO"]', style: { "border-color": SENTIMENT.NEGATIVO.color } },
  { selector: 'edge[sentiment = "POSITIVO"]', style: { "line-color": "#166534", "target-arrow-color": "#166534" } },
  { selector: 'edge[sentiment = "NEUTRAL"]', style: { "line-color": "#854d0e", "target-arrow-color": "#854d0e" } },
  { selector: 'edge[sentiment = "NEGATIVO"]', style: { "line-color": "#991b1b", "target-arrow-color": "#991b1b" } },
  { selector: ".fresh", style: { "border-width": 6, "border-color": "#f8fafc" } },
  { selector: "node.dim", style: { opacity: 0.07, "text-opacity": 0 } },
  { selector: "edge.dim", style: { opacity: 0.04, "text-opacity": 0 } },
  { selector: "node.focus", style: { opacity: 1, "text-opacity": 1, "z-index": 30, "border-width": 5 } },
  { selector: "edge.focus", style: { opacity: 0.95, "text-opacity": 1, "z-index": 20, width: "mapData(ew, 0, 1, 1.4, 4.6)" } },
  { selector: ":selected", style: { "border-color": "#f8fafc", "border-width": 6 } },
];

const LAYOUT = {
  name: "cose",
  animate: true,
  animationDuration: 550,
  randomize: false,
  fit: true,
  padding: 40,
  nodeRepulsion: 12000,
  idealEdgeLength: 85,
  nodeOverlap: 24,
  numIter: 500,
};

export default function SessionGraph({ graph, onReset, brand = "Marca" }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const [selected, setSelected] = useState(null);
  const [kinds, setKinds] = useState({
    MARCA: true,
    PLATAFORMA: true,
    PALABRA: true,
    USUARIO: false,
  });

  const counts = useMemo(() => {
    const acc = {};
    graph.nodes.forEach((n) => {
      acc[n.label] = (acc[n.label] || 0) + 1;
    });
    return acc;
  }, [graph]);

  const visible = useMemo(() => {
    const nodes = graph.nodes.filter((n) => kinds[n.label]);
    const ids = new Set(nodes.map((n) => n.node_id));
    const edges = graph.edges.filter((e) => ids.has(e.src) && ids.has(e.dst));
    return { nodes, edges };
  }, [graph, kinds]);

  const clearFocus = () => cyRef.current?.elements().removeClass("dim focus");

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
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const logW = (v) => Math.log(Math.max(2, Number(v) || 1));
    const nw = visible.nodes.map((n) => logW(n.weight));
    const nLo = nw.length ? Math.min(...nw) : 0;
    const nHi = nw.length ? Math.max(...nw) : 1;
    const nSize = (n) => (nHi > nLo ? (logW(n.weight) - nLo) / (nHi - nLo) : 0.6);
    const ews = visible.edges.map((e) => logW(e.weight));
    const eLo = ews.length ? Math.min(...ews) : 0;
    const eHi = ews.length ? Math.max(...ews) : 1;
    const eSize = (e) => (eHi > eLo ? (logW(e.weight) - eLo) / (eHi - eLo) : 0.5);

    const wanted = new Set(visible.nodes.map((n) => n.node_id));
    const edgesWanted = new Set(visible.edges.map((e) => e.edge_id));
    let added = false;

    cy.nodes().forEach((n) => {
      if (!wanted.has(n.id())) n.remove();
    });
    cy.edges().forEach((e) => {
      if (!edgesWanted.has(e.id())) e.remove();
    });

    visible.nodes.forEach((n) => {
      const existing = cy.getElementById(n.node_id);
      if (existing.nonempty()) {
        existing.data({ weight: n.weight, sentiment: n.sentiment, size: nSize(n) });
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
        added = true;
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
      }
    });

    if (added) {
      cy.elements().removeClass("dim focus");
      const latest = cy.nodes().last();
      latest.addClass("fresh");
      cy.layout(LAYOUT).run();
      setTimeout(() => latest.removeClass("fresh"), 900);
    }
  }, [visible]);

  const empty = visible.nodes.length === 0;
  const hasHidden = graph.nodes.length > 0 && visible.nodes.length < graph.nodes.length;

  return (
    <div className="panel graph-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0 }}>Grafo de esta sesión</h2>
          <p className="panel-sub" style={{ marginBottom: 0 }}>
            Se arma en vivo con cada mensaje nuevo mientras esta pestaña está abierta (no se guarda).
            Por defecto se ocultan los autores para no ensuciar; activalos si querés verlos.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>
            {visible.nodes.length} de {graph.nodes.length} nodos · {visible.edges.length} aristas
          </span>
          <button className="ghost" onClick={onReset}>
            reiniciar sesión
          </button>
        </div>
      </div>

      <div className="graph-tools">
        {KIND_ORDER.map((kind) => (
          <button
            key={kind}
            className={`chip ${kinds[kind] ? "on" : ""}`}
            onClick={() => setKinds((prev) => ({ ...prev, [kind]: !prev[kind] }))}
          >
            <span className="swatch" style={{ background: LABEL_COLOR[kind] }} />
            {LABEL_TEXT[kind]}
            <span className="mono count">{counts[kind] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="graph-wrap session-wrap" ref={containerRef}>
        {empty ? (
          <div className="graph-empty">
            <div className="graph-empty-dot" />
            {hasHidden
              ? "Esos nodos están filtrados. Activá algún tipo arriba."
              : "Esperando mensajes… los nodos van a ir apareciendo de a poco."}
          </div>
        ) : null}
      </div>

      <div className="legend">
        <span className="item">
          <span className="swatch" style={{ background: LABEL_COLOR.MARCA }} /> marca
        </span>
        <span className="item">
          <span className="swatch" style={{ background: LABEL_COLOR.PLATAFORMA }} /> plataforma
        </span>
        <span className="item">
          <span className="swatch" style={{ background: LABEL_COLOR.PALABRA }} /> palabra clave
        </span>
        <span className="item">
          <span className="swatch" style={{ background: LABEL_COLOR.USUARIO }} /> autor
        </span>
        <span className="item" style={{ marginLeft: "auto" }}>
          borde = sentimiento · {LABEL_TEXT.MARCA} = {brand} · clic para aislar un nodo
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
            <span className="pill mono">aparece {selected.weight}×</span>
            <span className="pill" style={{ color: SENTIMENT[selected.sentiment]?.color }}>
              {SENTIMENT[selected.sentiment]?.label ?? selected.sentiment}
            </span>
            <span className="pill mono">+{selected.pos ?? 0}</span>
            <span className="pill mono">~{selected.neu ?? 0}</span>
            <span className="pill mono">-{selected.neg ?? 0}</span>
            <button
              className="ghost"
              style={{ marginLeft: "auto" }}
              onClick={() => {
                clearFocus();
                setSelected(null);
              }}
            >
              quitar foco
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
