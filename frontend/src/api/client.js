// Cliente HTTP hacia la API Django (sesión + CSRF).
const BASE = import.meta.env.VITE_API_URL || "";

function cookie(nombre) {
  const m = document.cookie.match(new RegExp("(^|; )" + nombre + "=([^;]*)"));
  return m ? decodeURIComponent(m[2]) : "";
}

export class ErrorApi extends Error {
  constructor(status, datos) {
    super(mensajeDeError(datos) || `Error ${status}`);
    this.status = status;
    this.datos = datos;
  }
}

// Convierte {"monto": ["..."], "detalle": [...]} en un texto legible.
export function mensajeDeError(datos) {
  if (!datos) return "";
  if (typeof datos === "string") return datos;
  if (Array.isArray(datos)) return datos.map(mensajeDeError).join(" ");
  if (datos.detail) return datos.detail;
  return Object.values(datos).map(mensajeDeError).join(" ");
}

export async function api(path, { method = "GET", body, query } = {}) {
  const qs = query ? "?" + new URLSearchParams(Object.entries(query).filter(([, v]) => v !== "" && v != null)) : "";
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRFToken"] = cookie("csrftoken");
  const res = await fetch(`${BASE}/api${path}${qs}`, {
    method, headers, credentials: "include", body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const datos = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ErrorApi(res.status, datos);
  return datos;
}

export const prepararCsrf = () => api("/core/csrf/");
