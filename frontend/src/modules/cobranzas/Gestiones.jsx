import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { Mensaje } from "../../components/Formulario.jsx";
import { fecha, monto } from "../../format.js";
import { RevisionGestion } from "../facturas/FacturaDetalle.jsx";
import { Alertas } from "../facturas/GestionForm.jsx";

function fechaHora(iso) {
  return new Date(iso).toLocaleString("es-PY", { dateStyle: "short", timeStyle: "short" });
}

export default function Gestiones({ usuario }) {
  const [pendientes, setPendientes] = useState([]);
  const [promesas, setPromesas] = useState([]);
  const [recientes, setRecientes] = useState([]);
  const [error, setError] = useState("");

  function cargar() {
    api("/cobranzas/gestiones/", { query: { revision: "pendiente" } }).then((r) => setPendientes(r.results)).catch((e) => setError(e.message));
    api("/cobranzas/gestiones/", { query: { promesas_pendientes: 1 } }).then((r) => setPromesas(r.results)).catch(() => {});
    api("/cobranzas/gestiones/").then((r) => setRecientes(r.results.slice(0, 20))).catch(() => {});
  }
  useEffect(cargar, []);

  async function decidir(g, decision, mensaje_final = "") {
    try { await api(`/cobranzas/gestiones/${g.id}/revisar/`, { method: "POST", body: { decision, mensaje_final } }); cargar(); }
    catch (e) { setError(e.message); }
  }
  const verFactura = (g) => g.facturas?.length ? <a href="#facturas">ver facturas</a> : null;

  return (
    <section className="pagina">
      <div className="pagina-cabecera"><div><p className="eyebrow">Cobranzas</p><h1>Gestiones de cobro</h1></div></div>
      <Mensaje error={error} />
      <div className="panel">
        <h2>Pendientes de revisión ({pendientes.length})</h2>
        <p className="ayuda">Gestiones con recomendaciones de buenas prácticas. Tesorería decide qué se comunica al cliente.</p>
        {pendientes.length === 0 && <p className="ayuda">No hay gestiones pendientes.</p>}
        <ul className="gestiones">
          {pendientes.map((g) => (
            <li key={g.id} className="gestion gestion-pendiente">
              <div className="gestion-cab"><strong>{g.cliente_razon_social} · {g.tipo.replace("_", " ")}</strong><span className="ayuda">{fechaHora(g.fecha_hora)} · {g.cobrador_nombre}</span></div>
              {g.mensaje && <p>{g.mensaje}</p>}
              <Alertas alertas={g.alertas} />
              {usuario.es_tesorero ? <RevisionGestion g={g} onDecidir={decidir} /> : <p className="msg msg-aviso">Esperando revisión de tesorería.</p>}
            </li>
          ))}
        </ul>
      </div>
      <div className="panel">
        <h2>Promesas de pago por evaluar ({promesas.length})</h2>
        <div className="tabla-scroll">
          <table>
            <thead><tr><th>Cliente</th><th>Fecha prometida</th><th className="der">Monto</th><th>Registrada por</th><th></th></tr></thead>
            <tbody>{promesas.map((g) => (
              <tr key={g.id}><td>{g.cliente_razon_social}</td><td>{fecha(g.promesa_fecha)}</td><td className="der num">{Number(g.promesa_monto).toLocaleString("es-PY")}</td><td>{g.cobrador_nombre}</td><td>{verFactura(g)}</td></tr>
            ))}
              {promesas.length === 0 && <tr><td colSpan={5} className="ayuda">Sin promesas pendientes.</td></tr>}</tbody>
          </table>
        </div>
      </div>
      <div className="panel">
        <h2>Últimas gestiones</h2>
        <div className="tabla-scroll">
          <table>
            <thead><tr><th>Fecha</th><th>Cliente</th><th>Tipo</th><th>Resultado</th><th>Cobrador</th><th>Revisión</th></tr></thead>
            <tbody>{recientes.map((g) => (
              <tr key={g.id}><td>{fechaHora(g.fecha_hora)}</td><td>{g.cliente_razon_social}</td><td>{g.tipo.replace("_", " ")}</td>
                <td>{(g.resultado || "—").replace("_", " ")}</td><td>{g.cobrador_nombre}</td><td>{g.revision.replace("_", " ")}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
