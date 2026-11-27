import { useEffect, useState } from "react";
import { api } from "./api/client.js";
import Auditoria from "./modules/admin/Auditoria.jsx";
import TasasBcp from "./modules/admin/TasasBcp.jsx";
import Usuarios from "./modules/admin/Usuarios.jsx";
import Clientes from "./modules/clientes/Clientes.jsx";
import Gestiones from "./modules/cobranzas/Gestiones.jsx";
import RegistrarCobranza from "./modules/cobranzas/RegistrarCobranza.jsx";
import Facturas from "./modules/facturas/Facturas.jsx";
import Reportes from "./modules/reportes/Reportes.jsx";
import Dashboard from "./modules/tesoreria/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import "./styles.css";

// [clave, título, componente, quién la ve]
const VISTAS = [
  ["dashboard", "Dashboard", Dashboard, () => true],
  ["facturas", "Facturas", Facturas, () => true],
  ["cobranza", "Registrar cobranza", RegistrarCobranza, () => true],
  ["gestiones", "Gestiones", Gestiones, () => true],
  ["clientes", "Clientes", Clientes, () => true],
  ["reportes", "Reportes", Reportes, () => true],
  ["tasas", "Tasas BCP", TasasBcp, (u) => u.es_tesorero],
  ["usuarios", "Usuarios", Usuarios, (u) => u.es_administrador],
  ["auditoria", "Auditoría", Auditoria, (u) => u.es_administrador],
];
const ROL = { administrador: "Administrador", tesorero: "Tesorero", cobrador: "Cobrador" };

function vistaDelHash(usuario) {
  const h = window.location.hash.replace("#", "");
  const v = VISTAS.find(([k, , , puede]) => k === h && (!usuario || puede(usuario)));
  return v ? h : "dashboard";
}

export default function App() {
  const [usuario, setUsuario] = useState(undefined); // undefined = verificando
  const [vista, setVista] = useState(vistaDelHash());

  useEffect(() => {
    api("/core/me/").then(setUsuario).catch(() => setUsuario(null));
  }, []);
  useEffect(() => {
    const alCambiar = () => setVista(vistaDelHash(usuario));
    alCambiar();
    window.addEventListener("hashchange", alCambiar);
    return () => window.removeEventListener("hashchange", alCambiar);
  }, [usuario]);

  async function salir() {
    await api("/core/logout/", { method: "POST" }).catch(() => {});
    setUsuario(null);
  }

  if (usuario === undefined) return <p className="cargando">Cargando…</p>;
  if (!usuario) return <Login onIngreso={setUsuario} />;
  const visibles = VISTAS.filter(([, , , puede]) => puede(usuario));
  const Vista = (visibles.find(([k]) => k === vista) || visibles[0])[2];

  return (
    <div className="app">
      <header className="barra">
        <a className="marca" href="#dashboard" aria-label="Hierro Metal S.R.L. · CRM Tesorería">
          <span className="placa-logo"><img src="/marca/logo-hierro-metal.jpg" alt="Hierro Metal S.R.L." width="96" height="96" /></span>
          <span className="marca-texto">CRM Tesorería</span>
        </a>
        <nav aria-label="Módulos" className="nav">
          {visibles.map(([k, t]) => (
            <a key={k} href={`#${k}`} className={vista === k ? "nav-activo" : ""} aria-current={vista === k ? "page" : undefined}>{t}</a>
          ))}
        </nav>
        <div className="usuario">
          <span>{usuario.first_name || usuario.username} · {ROL[usuario.rol] || usuario.rol}</span>
          {usuario.es_administrador && <a href="/admin/">Panel técnico</a>}
          <button type="button" className="link" onClick={salir}>Salir</button>
        </div>
      </header>
      <main className="contenido">
        <Vista usuario={usuario} />
      </main>
      <footer className="pie">Hierro Metal S.R.L. · RUC 80013339-0 · Uso interno de Tesorería</footer>
    </div>
  );
}
