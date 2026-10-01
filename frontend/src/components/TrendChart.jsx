import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SENTIMENT } from "../theme";

const clock = (value) =>
  new Date(value).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });

export default function TrendChart({ trend }) {
  const points = trend?.points ?? [];
  return (
    <div className="panel">
      <h2>Tendencia por minuto · {trend?.minutes ?? 30}m</h2>
      <p className="panel-sub">
        Cuántas menciones de cada sentimiento llegaron por minuto. Así se ve si la opinión sube o baja con el tiempo.
      </p>
      {points.length === 0 ? (
        <div className="empty">Esperando micro-lotes…</div>
      ) : (
        <ResponsiveContainer width="100%" height={230}>
          <AreaChart data={points} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
            <defs>
              {["POSITIVO", "NEUTRAL", "NEGATIVO"].map((key) => (
                <linearGradient key={key} id={`g-${key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={SENTIMENT[key].color} stopOpacity={0.55} />
                  <stop offset="100%" stopColor={SENTIMENT[key].color} stopOpacity={0.04} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis dataKey="bucket" tickFormatter={clock} stroke="#64748b" fontSize={11} minTickGap={24} />
            <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
            <Tooltip
              labelFormatter={clock}
              contentStyle={{
                background: "#0b1424",
                border: "1px solid #1f2937",
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Area
              type="monotone"
              dataKey="POSITIVO"
              stackId="1"
              stroke={SENTIMENT.POSITIVO.color}
              fill="url(#g-POSITIVO)"
            />
            <Area
              type="monotone"
              dataKey="NEUTRAL"
              stackId="1"
              stroke={SENTIMENT.NEUTRAL.color}
              fill="url(#g-NEUTRAL)"
            />
            <Area
              type="monotone"
              dataKey="NEGATIVO"
              stackId="1"
              stroke={SENTIMENT.NEGATIVO.color}
              fill="url(#g-NEGATIVO)"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
