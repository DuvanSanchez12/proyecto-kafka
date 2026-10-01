import { SENTIMENT } from "../theme";

export default function Badge({ value }) {
  const s = SENTIMENT[value] || { color: "#64748b", label: value || "?" };
  return (
    <span
      className="badge"
      style={{
        background: `${s.color}22`,
        color: s.color,
        border: `1px solid ${s.color}55`,
      }}
    >
      {s.label}
    </span>
  );
}
