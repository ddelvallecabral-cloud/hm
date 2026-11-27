import { useEffect, useState } from "react";
import { api } from "./api/client.js";
import RegistrarCobranza from "./modules/cobranzas/RegistrarCobranza.jsx";
import Login from "./pages/Login.jsx";
import "./styles.css";

export default function App() {
  const [usuario, setUsuario] = useState(undefined); // undefined = verificando

  useEffect(() => {
    api("/core/me/").then(setUsuario).catch(() => setUsuario(null));
  }, []);

  async function salir() {
    await api("/core/logout/", { method: "POST" }).catch(() => {});
    setUsuario(null);
  }

  if (usuario === undefined) return <p className="cargando">Cargando…</p>;
  if (!usuario) return <Login onIngreso={setUsuario} />;

  return (
    <div className="app">
      <header className="barra">
        <div className="marca">CRM Tesorería</div>
        <nav aria-label="Módulos"><span className="nav-activo">Registrar cobranza</span></nav>
        <div className="usuario">
          <span>{usuario.first_name || usuario.username} · {usuario.rol}</span>
          <a href="/admin/">Administración</a>
          <button type="button" className="link" onClick={salir}>Salir</button>
        </div>
      </header>
      <main className="contenido">
        <RegistrarCobranza usuario={usuario} />
      </main>
    </div>
  );
}
