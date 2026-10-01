const BASE = import.meta.env.VITE_API_BASE || "/api";

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new Error(`${path} -> HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => get("/health"),
  kpis: () => get("/kpis"),
  trend: (minutes = 30) => get(`/trend?minutes=${minutes}`),
  graph: (limit = 140) => get(`/graph?limit=${limit}`),
  messages: (limit = 25) => get(`/messages?limit=${limit}`),
  accuracy: () => get("/accuracy"),
  complexity: (limit = 40) => get(`/complexity?limit=${limit}`),
};
