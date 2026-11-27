import { useEffect, useState } from "react";
import { api } from "./api/client.js";
import RegistrarCobranza from "./modules/cobranzas/RegistrarCobranza.jsx";
import Reportes from "./modules/reportes/Reportes.jsx";
import Dashboard from "./modules/tesoreria/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import "./styles.css";

const VISTAS = [
  ["dashboard", "Dashboard", Dashboard],
  ["cobranza", "Registrar cobranza", RegistrarCobranza],
  ["reportes", "Reportes", Reportes],
];

function vistaDelHash() {
  const h = window.location.hash.replace("#", "");
  return VISTAS.some(([k]) => k === h) ? h : "dashboard";
}

export default function App() {
  const [usuario, setUsuario] = useState(undefined); // undefined = verificando
  const [vista, setVista] = useState(vistaDelHash());

  useEffect(() => {
    api("/core/me/").then(setUsuario).catch(() => setUsuario(null));
    const alCambiar = () => setVista(vistaDelHash());
    window.addEventListener("hashchange", alCambiar);
    return () => window.removeEventListener("hashchange", alCambiar);
  }, []);

  async function salir() {
    await api("/core/logout/", { method: "POST" }).catch(() => {});
    setUsuario(null);
  }

  if (usuario === undefined) return <p className="cargando">Cargando…</p>;
  if (!usuario) return <Login onIngreso={setUsuario} />;
  const Vista = VISTAS.find(([k]) => k === vista)[2];

  return (
    <div className="app">
      <header className="barra">
        <div className="marca">CRM Tesorería</div>
        <nav aria-label="Módulos" className="nav">
          {VISTAS.map(([k, t]) => (
            <a key={k} href={`#${k}`} className={vista === k ? "nav-activo" : ""} aria-current={vista === k ? "page" : undefined}>{t}</a>
          ))}
        </nav>
        <div className="usuario">
          <span>{usuario.first_name || usuario.username} · {usuario.rol}</span>
          <a href="/admin/">Administración</a>
          <button type="button" className="link" onClick={salir}>Salir</button>
        </div>
      </header>
      <main className="contenido">
        <Vista usuario={usuario} />
      </main>
    </div>
  );
}
