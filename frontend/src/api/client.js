// Cliente HTTP mínimo hacia la API Django.
const BASE = import.meta.env.VITE_API_URL || "";

export async function api(path, options = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
