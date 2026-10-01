import { useState } from "react";
import { api } from "./api";
import { usePolling, useSessionGraph } from "./hooks";
import KpiRow from "./components/KpiRow";
import TrendChart from "./components/TrendChart";
import LiveFeed from "./components/LiveFeed";
import GraphView from "./components/GraphView";
import SessionGraph from "./components/SessionGraph";
import ComplexityPanel from "./components/ComplexityPanel";
import HowItWorks from "./components/HowItWorks";

export default function App() {
  const [minutes] = useState(30);

  const health = usePolling(api.health, 5000);
  const kpis = usePolling(api.kpis, 4000);
  const trend = usePolling(() => api.trend(minutes), 8000, [minutes]);
  const graph = usePolling(() => api.graph(400), 7000);
  const feed = usePolling(() => api.messages(8), 8000);
  const complexity = usePolling(() => api.complexity(40), 9000);

  const brand = health.data?.brand ?? "Marca";
  const { graph: sessionGraph, reset: resetSession } = useSessionGraph(feed.data?.messages, brand);

  const live = health.data?.status === "ok" && (health.data?.mentions ?? 0) > 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>
            Brand<span className="brand-name">{health.data?.brand ?? "Pulse"}</span>
          </h1>
          <span className="tag">sentimiento en vivo · Kafka → Spark → Postgres → API</span>
        </div>
        <div className="status">
          <span className={`dot ${live ? "live" : ""}`} />
          {live ? `en vivo · lote #${health.data?.last_batch}` : "esperando datos…"}
        </div>
      </header>

      {health.error ? (
        <div className="panel banner error" style={{ marginBottom: 16 }}>
          Sin conexión con la API ({String(health.error.message || health.error)})
        </div>
      ) : null}

      <HowItWorks />

      <KpiRow kpis={kpis.data} />

      <div className="grid">
        <GraphView graph={graph.data} />
        <div className="stack">
          <TrendChart trend={trend.data} />
          <LiveFeed messages={feed.data} />
        </div>
      </div>

      <SessionGraph graph={sessionGraph} onReset={resetSession} brand={brand} />

      <ComplexityPanel complexity={complexity.data} />
    </div>
  );
}
