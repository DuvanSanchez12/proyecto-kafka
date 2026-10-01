import Badge from "./Badge";

export default function LiveFeed({ messages }) {
  const items = messages?.messages ?? [];
  return (
    <div className="panel">
      <h2>Mensajes en vivo</h2>
      <p className="panel-sub">
        Últimos mensajes ya clasificados. Va lento a propósito, de a poco, para que se puedan leer.
        Cada mensaje nuevo alimenta el grafo de la sesión que está más abajo.
      </p>
      {items.length === 0 ? (
        <div className="empty">Esperando mensajes del productor…</div>
      ) : (
        <div className="feed">
          {items.map((m) => (
            <article className="msg" key={m.mention_id}>
              <div className="msg-head">
                <span>
                  @{m.author} · {m.platform}
                </span>
                <Badge value={m.sentiment} />
              </div>
              <p className="msg-text">{m.text}</p>
              <div className="msg-foot">
                <span className="pill mono">score {(m.score ?? 0).toFixed(2)}</span>
                <span className="pill mono">conf {(m.confidence ?? 0).toFixed(2)}</span>
                {(m.keywords ?? []).map((k) => (
                  <span className="pill" key={k}>
                    #{k}
                  </span>
                ))}
                <span
                  className="pill"
                  style={{ color: m.correct ? "var(--pos)" : "var(--neg)" }}
                >
                  {m.correct ? "✓ etiqueta coincidente" : `✗ esperado ${m.expected ?? "?"}`}
                </span>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
