import { useEffect, useState } from "react";
import { api } from "./api/client.js";

// Esqueleto: las pantallas de cada módulo se agregan en src/modules/<modulo>.
const MODULOS = ["Clientes", "Facturación", "Cobranzas", "Intereses", "Tesorería", "Reportes"];

export default function App() {
  const [estado, setEstado] = useState("verificando…");
  useEffect(() => {
    api("/health/").then((r) => setEstado(r.status)).catch(() => setEstado("sin conexión"));
  }, []);
  return (
    <main style={{ fontFamily: "system-ui", padding: 16, maxWidth: 720, margin: "0 auto" }}>
      <h1>CRM Tesorería</h1>
      <p>Estado de la API: <strong>{estado}</strong></p>
      <ul>{MODULOS.map((m) => <li key={m}>{m} — pendiente</li>)}</ul>
    </main>
  );
}
