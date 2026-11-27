import { useState } from "react";
import { api } from "../../api/client.js";
import { Campo, Mensaje } from "../../components/Formulario.jsx";
import { normalizarMonto } from "../../format.js";

const TIPOS = [["llamada", "Llamada"], ["email", "Correo"], ["whatsapp", "WhatsApp / SMS"], ["visita", "Visita"], ["carta", "Nota / carta"], ["nota_interna", "Nota interna"]];
const RESULTADOS = [["", "—"], ["contactado", "Contactado"], ["no_contesta", "No contesta"], ["promesa_pago", "Promesa de pago"], ["reclamo", "Reclamo / disputa"], ["informa_pago", "Informa pago realizado"], ["derivado_legal", "Derivado a asesoría legal"]];

function ahoraLocal() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export function Alertas({ alertas }) {
  if (!alertas?.length) return null;
  return (
    <div className="alertas">
      <strong>Recomendaciones antes de comunicar</strong>
      <ul>{alertas.map((a, i) => <li key={i}>{a.mensaje} <span className="ayuda">{a.sugerencia}</span></li>)}</ul>
    </div>
  );
}

export default function GestionForm({ factura, onGuardada }) {
  const [g, setG] = useState({ tipo: "llamada", fecha_hora: ahoraLocal(), destinatario: "titular", resultado: "", mensaje: "", promesa_fecha: "", promesa_monto: "", proxima_accion: "" });
  const [rec, setRec] = useState(null);
  const [alertas, setAlertas] = useState(null);
  const [error, setError] = useState("");
  const campo = (k) => (e) => { setG((v) => ({ ...v, [k]: e.target.value })); setAlertas(null); };

  function cuerpo() {
    const c = { ...g, cliente: factura.cliente, facturas: [factura.id], fecha_hora: new Date(g.fecha_hora).toISOString() };
    for (const k of ["promesa_fecha", "proxima_accion"]) if (!c[k]) c[k] = null;
    c.promesa_monto = c.promesa_monto ? normalizarMonto(c.promesa_monto, factura.moneda) : null;
    return c;
  }

  async function sugerir() {
    try {
      const r = await api("/cobranzas/recomendaciones/", { query: { factura: factura.id } });
      setRec(r); setG((v) => ({ ...v, mensaje: r.mensaje_sugerido }));
    } catch (e) { setError(e.message); }
  }
  async function verificar() {
    setError("");
    try { setAlertas((await api("/cobranzas/gestiones/verificar/", { method: "POST", body: cuerpo() })).alertas); }
    catch (e) { setError(e.message); }
  }
  async function guardar(e) {
    e.preventDefault();
    setError("");
    try {
      const r = await api("/cobranzas/gestiones/", { method: "POST", body: cuerpo() });
      onGuardada(r);
      setG((v) => ({ ...v, resultado: "", mensaje: "", promesa_fecha: "", promesa_monto: "", fecha_hora: ahoraLocal() }));
      setAlertas(null); setRec(null);
    } catch (err) { setError(err.message); }
  }

  return (
    <form className="subpanel" onSubmit={guardar}>
      <h3>Registrar gestión de cobro</h3>
      <div className="grilla">
        <Campo id="g-tipo" label="Tipo"><select id="g-tipo" value={g.tipo} onChange={campo("tipo")}>{TIPOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Campo>
        <Campo id="g-fh" label="Fecha y hora"><input id="g-fh" type="datetime-local" value={g.fecha_hora} onChange={campo("fecha_hora")} required /></Campo>
        <Campo id="g-dest" label="Con quién"><select id="g-dest" value={g.destinatario} onChange={campo("destinatario")}><option value="titular">Titular o representante</option><option value="contacto_autorizado">Contacto autorizado</option></select></Campo>
        <Campo id="g-res" label="Resultado"><select id="g-res" value={g.resultado} onChange={campo("resultado")}>{RESULTADOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Campo>
        {g.resultado === "promesa_pago" && <>
          <Campo id="g-pf" label="Fecha prometida"><input id="g-pf" type="date" value={g.promesa_fecha} onChange={campo("promesa_fecha")} required /></Campo>
          <Campo id="g-pm" label={`Monto prometido (${factura.moneda})`}><input id="g-pm" inputMode="decimal" value={g.promesa_monto} onChange={campo("promesa_monto")} required /></Campo>
        </>}
        <Campo id="g-prox" label="Próxima acción"><input id="g-prox" type="date" value={g.proxima_accion} onChange={campo("proxima_accion")} /></Campo>
        <Campo id="g-msg" label="Mensaje o resumen" ancho><textarea id="g-msg" rows={4} value={g.mensaje} onChange={campo("mensaje")} /></Campo>
      </div>
      {rec && <p className="ayuda">Sugerencia para {rec.dias_atraso} días de atraso: tono {rec.tono.toLowerCase()}, canal {rec.canal_sugerido.toLowerCase()}.</p>}
      <Alertas alertas={alertas} />
      {alertas && alertas.length === 0 && <p className="msg msg-ok">Sin observaciones.</p>}
      <Mensaje error={error} />
      <div className="acciones">
        <button type="submit">Guardar gestión</button>
        <button type="button" className="secundario" onClick={sugerir}>Usar mensaje sugerido</button>
        <button type="button" className="secundario" onClick={verificar}>Revisar recomendaciones</button>
      </div>
    </form>
  );
}
