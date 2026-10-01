import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const fmt = (value) => Number(value ?? 0).toLocaleString("es");

function Stat({ label, value, hint, accent }) {
  return (
    <div style={{ background: "#0b1424", border: "1px solid #16203a", borderRadius: 10, padding: "10px 12px" }}>
      <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: accent || "var(--text)" }}>
        {value}
      </div>
      <div className="label" style={{ marginTop: 4 }}>{label}</div>
      {hint ? <div className="sub" style={{ marginTop: 4 }}>{hint}</div> : null}
    </div>
  );
}

export default function ComplexityPanel({ complexity }) {
  const batches = [...(complexity?.batches ?? [])].reverse();
  const total = complexity?.total ?? {};
  const ratio = total.comparaciones_teoricas
    ? (total.comparaciones_reales / total.comparaciones_teoricas).toFixed(2)
    : "—";

  return (
    <div className="panel">
      <h2>Complejidad empírica · divide y vencerás + merge sort</h2>
      <p className="panel-sub">
        Mide el trabajo real del algoritmo por micro-lote. <strong>Comparaciones reales</strong> son las que hizo;
        la <strong>cota Θ(n log n)</strong> es el techo teórico; <strong>mezclas</strong> son los nodos internos del
        árbol de divide y vencerás.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12, marginBottom: 14 }}>
        <Stat
          label="Comparaciones reales"
          value={fmt(total.comparaciones_reales)}
          hint="medidas en ejecución"
          accent="var(--accent)"
        />
        <Stat
          label="Cota teórica Θ(n log n)"
          value={fmt(total.comparaciones_teoricas)}
          hint={`real / teórica = ${ratio}`}
        />
        <Stat label="Mezclas Merge(A, B)" value={fmt(total.mezclas)} hint="nodos internos del árbol" />
        <Stat label="Profundidad máxima" value={fmt(total.niveles)} hint={`sobre ${fmt(total.tokens)} tokens`} />
      </div>

      {batches.length === 0 ? (
        <div className="empty">Sin micro-lotes registrados…</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={batches} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
              <XAxis dataKey="batch_index" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip
                contentStyle={{ background: "#0b1424", border: "1px solid #1f2937", borderRadius: 8, fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="dnc_comparisons"
                name="comparaciones reales"
                stroke="#38bdf8"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="theoretical_min"
                name="cota Θ(n log n)"
                stroke="#f472b6"
                strokeDasharray="5 4"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>

          <table className="mini" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Lote</th>
                <th>Mensajes</th>
                <th>Tokens</th>
                <th>Comparaciones</th>
                <th>Cota</th>
                <th>Mezclas</th>
                <th>Niveles</th>
              </tr>
            </thead>
            <tbody>
              {batches.slice(-8).reverse().map((b) => (
                <tr key={b.batch_index}>
                  <td className="mono">#{b.batch_index}</td>
                  <td className="mono">{fmt(b.messages)}</td>
                  <td className="mono">{fmt(b.total_tokens)}</td>
                  <td className="mono">{fmt(b.dnc_comparisons)}</td>
                  <td className="mono" style={{ color: "var(--muted)" }}>{fmt(b.theoretical_min)}</td>
                  <td className="mono">{fmt(b.merge_operations)}</td>
                  <td className="mono">{fmt(b.dnc_levels)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
