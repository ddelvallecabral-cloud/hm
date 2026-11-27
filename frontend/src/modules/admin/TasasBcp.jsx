import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { Campo, Mensaje } from "../../components/Formulario.jsx";

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

export default function TasasBcp({ usuario }) {
  const hoy = new Date();
  const [lista, setLista] = useState([]);
  const [alertas, setAlertas] = useState([]);
  const [t, setT] = useState({ anio: hoy.getFullYear(), mes: hoy.getMonth() + 1, moneda: "PYG", tasa_maxima_anual: "", fuente: "" });
  const [msg, setMsg] = useState({});
  const cargar = () => {
    api("/intereses/tasas-bcp/").then((r) => setLista(r.results)).catch((e) => setMsg({ error: e.message }));
    api("/intereses/alertas/", { query: { revisada: "false" } }).then((r) => setAlertas(r.results)).catch(() => {});
  };
  useEffect(cargar, []);
  const campo = (k) => (e) => setT((v) => ({ ...v, [k]: e.target.value }));

  async function guardar(e) {
    e.preventDefault();
    try {
      await api("/intereses/tasas-bcp/", { method: "POST", body: { ...t, tasa_maxima_anual: String(t.tasa_maxima_anual).replace(",", ".") } });
      setMsg({ ok: `Tasa ${MESES[t.mes - 1]} ${t.anio} ${t.moneda} cargada.` }); setT((v) => ({ ...v, tasa_maxima_anual: "" })); cargar();
    } catch (err) { setMsg({ error: err.message }); }
  }
  async function revisada(a) { await api(`/intereses/alertas/${a.id}/revisada/`, { method: "POST" }).catch(() => {}); cargar(); }

  const meses = [...new Set(lista.map((x) => `${x.anio}-${String(x.mes).padStart(2, "0")}`))].sort().reverse();
  const tasa = (clave, moneda) => lista.find((x) => `${x.anio}-${String(x.mes).padStart(2, "0")}` === clave && x.moneda === moneda);

  return (
    <section className="pagina">
      <div className="pagina-cabecera"><div><p className="eyebrow">Intereses por mora</p><h1>Tasas máximas del BCP</h1></div></div>
      <Mensaje error={msg.error} ok={msg.ok} />
      {usuario.es_administrador && (
        <form className="panel" onSubmit={guardar}>
          <h2>Cargar tasa del mes</h2>
          <p className="ayuda">Cargue cada mes las dos tasas (PYG y USD) publicadas por el BCP, con la resolución o comunicado como fuente.</p>
          <div className="grilla">
            <Campo id="t-mes" label="Mes"><select id="t-mes" value={t.mes} onChange={campo("mes")}>{MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select></Campo>
            <Campo id="t-anio" label="Año"><input id="t-anio" type="number" value={t.anio} onChange={campo("anio")} /></Campo>
            <Campo id="t-mon" label="Moneda"><select id="t-mon" value={t.moneda} onChange={campo("moneda")}><option value="PYG">Guaraníes</option><option value="USD">Dólares</option></select></Campo>
            <Campo id="t-tasa" label="Tasa máxima anual (%)"><input id="t-tasa" inputMode="decimal" placeholder="27,26" value={t.tasa_maxima_anual} onChange={campo("tasa_maxima_anual")} required /></Campo>
            <Campo id="t-fte" label="Fuente" ancho><input id="t-fte" placeholder="Resolución / comunicado del BCP" value={t.fuente} onChange={campo("fuente")} required /></Campo>
          </div>
          <div className="acciones"><button type="submit">Guardar tasa</button></div>
        </form>
      )}
      <div className="panel tabla-scroll">
        <table>
          <thead><tr><th>Mes</th><th className="der">PYG % anual</th><th className="der">USD % anual</th><th>Fuente</th></tr></thead>
          <tbody>{meses.map((m) => {
            const p = tasa(m, "PYG"), u = tasa(m, "USD");
            return (<tr key={m}><td>{MESES[Number(m.slice(5)) - 1]} {m.slice(0, 4)}</td>
              <td className="der num">{p ? Number(p.tasa_maxima_anual).toLocaleString("es-PY") : "falta"}</td>
              <td className="der num">{u ? Number(u.tasa_maxima_anual).toLocaleString("es-PY") : "falta"}</td>
              <td>{(p || u).fuente}</td></tr>);
          })}</tbody>
        </table>
      </div>
      <div className="panel">
        <h2>Alertas de tasa ({alertas.length})</h2>
        <p className="ayuda">Facturas cuya tasa pactada se ajustó al tope legal, o calculadas con la tasa de un mes anterior por falta de carga.</p>
        <ul className="gestiones">{alertas.map((a) => (
          <li key={a.id} className="gestion"><div className="gestion-cab"><strong className="mono">{a.factura_numero}</strong><span className="ayuda">{a.cliente}</span></div>
            <p>{a.mensaje}</p>{usuario.es_tesorero && <button type="button" className="secundario" onClick={() => revisada(a)}>Marcar revisada</button>}</li>))}
          {alertas.length === 0 && <li className="ayuda">Sin alertas pendientes.</li>}</ul>
      </div>
    </section>
  );
}
