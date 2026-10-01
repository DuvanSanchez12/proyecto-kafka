const STAGES = [
  {
    n: "1",
    title: "Productor",
    text: "Genera menciones sintéticas de la marca (texto, autor, plataforma, hashtags y la etiqueta correcta) y las publica en Kafka.",
    color: "#f59e0b",
  },
  {
    n: "2",
    title: "Kafka",
    text: "Topic 'menciones' con 3 particiones. Es el buffer: desacopla al productor del consumidor y resiste picos.",
    color: "#38bdf8",
  },
  {
    n: "3",
    title: "Spark Streaming",
    text: "Cada 10 s lee el lote nuevo, corre el clasificador divide y vencerás + merge sort en paralelo y escribe en Postgres.",
    color: "#a78bfa",
  },
  {
    n: "4",
    title: "Postgres",
    text: "Guarda cada mención, los KPIs, la tendencia por minuto, el grafo de co-ocurrencia y la telemetría de complejidad.",
    color: "#34d399",
  },
  {
    n: "5",
    title: "API + Dashboard",
    text: "FastAPI sirve los datos ya agregados y este dashboard los muestra en vivo.",
    color: "#f472b6",
  },
];

const ALGO = [
  ["Partir", "El texto se normaliza a tokens y el arreglo se parte a la mitad recursivamente hasta el caso base (2 tokens)."],
  ["Resolver", "Cada token se puntúa con un léxico: polaridad, intensificadores y negaciones."],
  ["Combinar", "Con merge sort se mezclan las dos mitades ordenadas por fuerza y se propaga la negación; sale un score."],
  ["Clasificar", "El score se compara con una banda neutra y se decide: POSITIVO, NEUTRAL o NEGATIVO."],
  ["Verificar", "Se contrasta con la etiqueta esperada para medir exactitud, y se compara el n.º de comparaciones reales contra la cota Θ(n log n)."],
];

export default function HowItWorks() {
  return (
    <div className="panel how">
      <h2>¿Cómo funciona el sistema?</h2>
      <p className="panel-sub">
        Un mensaje entra por la izquierda y termina como un dato visible a la derecha. Todo el camino es automático y en vivo.
      </p>

      <div className="pipeline">
        {STAGES.map((s, i) => (
          <div className="stage-wrap" key={s.n}>
            <div className="stage">
              <span className="stage-n" style={{ background: `${s.color}22`, color: s.color, borderColor: `${s.color}66` }}>
                {s.n}
              </span>
              <strong style={{ color: s.color }}>{s.title}</strong>
              <span className="stage-text">{s.text}</span>
            </div>
            {i < STAGES.length - 1 ? <span className="arrow">→</span> : null}
          </div>
        ))}
      </div>

      <div className="algo">
        <h3>El clasificador, paso a paso (divide y vencerás + merge sort)</h3>
        <ol>
          {ALGO.map(([t, d]) => (
            <li key={t}>
              <strong>{t}:</strong> {d}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
