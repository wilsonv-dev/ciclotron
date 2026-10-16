// Única capa que conoce las URLs del backend.
// Si sirves el frontend desde otro origen, define antes: window.CYCLOTRON_API_BASE = "http://127.0.0.1:8000"
const BASE = window.CYCLOTRON_API_BASE ?? "";

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("No se pudo conectar con el backend. ¿Está ejecutándose uvicorn?");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    const msgs = Array.isArray(d)
      ? d.map((x) => (x.campo ? `${x.campo}: ${x.mensaje}` : x.mensaje))
      : [typeof d === "string" ? d : `Error HTTP ${res.status}`];
    throw new Error(msgs.join("; "));
  }
  return data;
}

export const api = {
  derived: (body) => request("POST", "/api/derived", body),
  createSimulation: (cfg) => request("POST", "/api/simulations", cfg),
  step: (id, n) => request("POST", `/api/simulations/${id}/step`, { n_steps: n }),
  reset: (id) => request("POST", `/api/simulations/${id}/reset`),
  state: (id) => request("GET", `/api/simulations/${id}/state`),
};