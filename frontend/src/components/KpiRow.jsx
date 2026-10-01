import Badge from "./Badge";
import { SENTIMENT } from "../theme";

const num = (value) => (value ?? 0).toLocaleString("es");

export default function KpiRow({ kpis }) {
  if (!kpis) {
    return (
      <section className="kpis">
        <div className="panel kpi"><div className="value mono">—</div><div className="label">cargando</div></div>
      </section>
    );
  }

  const dist = [
    { key: "POSITIVO", pct: kpis.pct_positivo ?? 0, count: kpis.positivos ?? 0 },
    { key: "NEUTRAL", pct: kpis.pct_neutral ?? 0, count: kpis.neutrales ?? 0 },
    { key: "NEGATIVO", pct: kpis.pct_negativo ?? 0, count: kpis.negativos ?? 0 },
  ];

  return (
    <section className="kpis">
      <div className="panel kpi">
        <div className="value mono">{num(kpis.total)}</div>
        <div className="label">Menciones procesadas</div>
        <div className="sub">
          {num(kpis.autores)} autores · {num(kpis.plataformas)} plataformas
        </div>
      </div>

      <div className="panel kpi">
        <div className="value mono" style={{ color: "var(--accent)" }}>
          {kpis.exactitud}%
        </div>
        <div className="label">Exactitud del algoritmo</div>
        <div className="sub">
          {num(kpis.correctos)} / {num(kpis.etiquetados)} etiquetadas correctamente
        </div>
      </div>

      <div className="panel kpi">
        <div className="value mono">{kpis.score_promedio ?? 0}</div>
        <div className="label">Score promedio</div>
        <div className="sub">confianza media {kpis.confianza_promedio ?? 0}</div>
      </div>

      <div className="panel kpi" style={{ gridColumn: "span 2" }}>
        <div className="label" style={{ marginTop: 0 }}>Distribución de sentimiento</div>
        <div style={{ display: "flex", gap: 16, marginTop: 10, flexWrap: "wrap" }}>
          {dist.map((d) => (
            <div key={d.key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Badge value={d.key} />
              <span className="mono" style={{ fontSize: 18, fontWeight: 700 }}>{d.pct}%</span>
              <span className="mono" style={{ color: "var(--muted)", fontSize: 12 }}>({num(d.count)})</span>
            </div>
          ))}
        </div>
        <div className="bar" style={{ marginTop: 12 }}>
          {dist.map((d) => (
            <span
              key={d.key}
              style={{ width: `${d.pct}%`, background: SENTIMENT[d.key].color }}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
