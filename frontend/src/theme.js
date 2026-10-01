export const SENTIMENT = {
  POSITIVO: { color: "#22c55e", label: "Positivo" },
  NEUTRAL: { color: "#eab308", label: "Neutral" },
  NEGATIVO: { color: "#ef4444", label: "Negativo" },
};

export const LABEL_COLOR = {
  MARCA: "#38bdf8",
  USUARIO: "#a78bfa",
  HASHTAG: "#f472b6",
  PALABRA: "#fbbf24",
  PLATAFORMA: "#34d399",
};

export const LABEL_TEXT = {
  MARCA: "Marca",
  USUARIO: "Usuario",
  HASHTAG: "Hashtag",
  PALABRA: "Palabra",
  PLATAFORMA: "Plataforma",
};

export function sentimentColor(value) {
  return (SENTIMENT[value] || { color: "#64748b" }).color;
}
