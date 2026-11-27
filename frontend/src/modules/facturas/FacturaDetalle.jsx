import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import Estado from "../../components/Estado.jsx";
import { Campo, Mensaje } from "../../components/Formulario.jsx";
import { fecha, monto } from "../../format.js";
import GestionForm, { Alertas } from "./GestionForm.jsx";

function fechaHora(iso) {
  return iso ? new Date(iso).toLocaleString("es-PY", { dateStyle: "short", timeStyle: "short" }) : "";
}

const ICONO_EVENTO = { pago: "Pago", gestion: "Gestión", auditoria: "Cambio" };

export default function FacturaDetalle({ id, usuario, onCambio }) {
  const [f, setF] = useState(null);
  const [interes, setInteres] = useState(null);
  const [hist, setHist] = useState(null);
  const [gestiones, setGestiones] = useState([]);
  const [prorroga, setProrroga] = useState({ fecha_vencimiento: "", motivo: "" });
  const [anular, setAnular] = useState("");
  const [msg, setMsg] = useState({});
  const tesorero = usuario.es_tesorero;

  async function cargar() {
    const fac = await api(`/facturacion/facturas/${id}/`);
    setF(fac);
    setProrroga({ fecha_vencimiento: fac.fecha_vencimiento, motivo: "" });
    api(`/intereses/facturas/${id}/`).then(setInteres).catch((e) => setInteres({ error: e.message }));
    api(`/facturacion/facturas/${id}/historial/`).then(setHist).catch(() => {});
    api("/cobranzas/gestiones/", { query: { factura: id } }).then((r) => setGestiones(r.results)).catch(() => {});
  }
  useEffect(() => { setF(null); setMsg({}); cargar().catch((e) => setMsg({ error: e.message })); }, [id]);

  async function guardarProrroga(e) {
    e.preventDefault();
    try {
      await api(`/facturacion/facturas/${id}/`, { method: "PATCH", body: prorroga });
      setMsg({ ok: "Vencimiento actualizado. El cambio quedó registrado en la auditoría." });
      await cargar(); onCambio?.();
    } catch (err) { setMsg({ error: err.message }); }
  }
  async function confirmarAnulacion(e) {
    e.preventDefault();
    try {
      await api(`/facturacion/facturas/${id}/anular/`, { method: "POST", body: { motivo: anular } });
      setMsg({ ok: "Factura anulada." }); setAnular("");
      await cargar(); onCambio?.();
    } catch (err) { setMsg({ error: err.message }); }
  }
  async function revisar(g, decision, mensaje_final = "") {
    try {
      await api(`/cobranzas/gestiones/${g.id}/revisar/`, { method: "POST", body: { decision, mensaje_final } });
      await cargar();
    } catch (err) { setMsg({ error: err.message }); }
  }

  if (!f) return <div className="panel"><Mensaje error={msg.error} />{!msg.error && <p className="ayuda">Cargando…</p>}</div>;
  const abierta = !["pagada", "anulada"].includes(f.estado);

  return (
    <div className="detalle">
      <div className="panel">
        <div className="cabecera">
          <div>
            <p className="eyebrow">Factura {f.condicion === "credito" ? `a crédito · ${f.plazo_dias} días` : "al contado"}</p>
            <h2 className="mono">{f.numero_completo}</h2>
            <p>{f.cliente_razon_social}{f.orden_compra_numero ? ` · OC ${f.orden_compra_numero}` : ""}</p>
          </div>
          <Estado estado={f.estado} />
        </div>
        <dl className="resumen">
          <div><dt>Emisión</dt><dd>{fecha(f.fecha_emision)}</dd></div>
          <div><dt>Vencimiento</dt><dd>{fecha(f.fecha_vencimiento)}</dd></div>
          <div><dt>Base imponible</dt><dd className="num">{monto(f.base_imponible, f.moneda)}</dd></div>
          <div><dt>IVA 10%</dt><dd className="num">{monto(f.iva, f.moneda)}</dd></div>
          <div><dt>Total</dt><dd className="num">{monto(f.total, f.moneda)}</dd></div>
          <div className="destacado"><dt>Saldo</dt><dd className="num">{monto(f.saldo, f.moneda)}</dd></div>
        </dl>
        <p className="ayuda">Timbrado {f.timbrado}{f.cdc ? ` · CDC ${f.cdc}` : ""} · SIFEN: {f.estado_sifen}
          {Number(f.tasa_interes_anual) ? ` · Tasa pactada ${Number(f.tasa_interes_anual).toLocaleString("es-PY")}% anual` : ""}
          {f.moneda === "USD" ? ` · TC ${f.tipo_cambio}` : ""}</p>
        {interes?.aplica && (
          <div className="interes">
            <p><strong>Interés por mora a hoy: {monto(interes.interes_acumulado, f.moneda)}</strong> ({interes.dias_atraso} días al {Number(interes.tasa_aplicada_anual).toLocaleString("es-PY")}% anual{interes.tasa_ajustada ? ", ajustada al tope legal" : ""}). Total con interés: {monto(interes.total, f.moneda)}.</p>
          </div>
        )}
        {interes?.error && <p className="msg msg-aviso">{interes.error}</p>}
        <div className="acciones">{abierta && <a className="boton" href={`#cobranza`}>Registrar cobranza</a>}</div>
        <Mensaje error={msg.error} ok={msg.ok} />
      </div>

      {tesorero && f.estado !== "anulada" && (
        <div className="panel">
          <h3>Acciones de tesorería</h3>
          <div className="dos-columnas-iguales">
            <form className="subpanel" onSubmit={guardarProrroga}>
              <h3>Prórroga de vencimiento</h3>
              <Campo id="p-fecha" label="Nuevo vencimiento"><input id="p-fecha" type="date" value={prorroga.fecha_vencimiento} onChange={(e) => setProrroga({ ...prorroga, fecha_vencimiento: e.target.value })} required /></Campo>
              <Campo id="p-mot" label="Motivo (obligatorio)"><input id="p-mot" value={prorroga.motivo} onChange={(e) => setProrroga({ ...prorroga, motivo: e.target.value })} required /></Campo>
              <div className="acciones"><button type="submit" disabled={prorroga.fecha_vencimiento === f.fecha_vencimiento}>Guardar prórroga</button></div>
            </form>
            {Number(f.saldo) === Number(f.total) && (
              <form className="subpanel" onSubmit={confirmarAnulacion}>
                <h3>Anular registro</h3>
                <p className="ayuda">Sólo si la factura fue anulada en el sistema de facturación o se cargó por error.</p>
                <Campo id="a-mot" label="Motivo (obligatorio)"><input id="a-mot" value={anular} onChange={(e) => setAnular(e.target.value)} required /></Campo>
                <div className="acciones"><button type="submit" className="peligro">Anular</button></div>
              </form>
            )}
          </div>
        </div>
      )}

      <div className="panel">
        <h3>Gestiones de cobro</h3>
        {gestiones.length === 0 && <p className="ayuda">Todavía no hay gestiones registradas para esta factura.</p>}
        <ul className="gestiones">
          {gestiones.map((g) => (
            <li key={g.id} className={"gestion" + (g.revision === "pendiente" ? " gestion-pendiente" : "")}>
              <div className="gestion-cab">
                <strong>{fechaHora(g.fecha_hora)} · {g.tipo.replace("_", " ")}{g.resultado ? ` · ${g.resultado.replace("_", " ")}` : ""}</strong>
                <span className="ayuda">{g.cobrador_nombre}</span>
              </div>
              {g.mensaje && <p>{g.mensaje}</p>}
              {g.promesa_fecha && <p className="ayuda">Promesa: {monto(g.promesa_monto, f.moneda)} para el {fecha(g.promesa_fecha)}{g.promesa_cumplida === true ? " · cumplida" : g.promesa_cumplida === false ? " · no cumplida" : ""}</p>}
              <Alertas alertas={g.alertas} />
              {g.revision === "pendiente" && (tesorero
                ? <RevisionGestion g={g} onDecidir={revisar} />
                : <p className="msg msg-aviso">Pendiente de revisión por tesorería.</p>)}
              {["aprobada", "modificada"].includes(g.revision) && <p className="ayuda">Revisada por {g.revisada_por_nombre}{g.revision === "modificada" ? `. Mensaje final: ${g.mensaje_final}` : ": aprobada."}</p>}
            </li>
          ))}
        </ul>
        {f.estado !== "anulada" && <GestionForm factura={{ id: f.id, cliente: f.cliente, moneda: f.moneda }} onGuardada={() => cargar()} />}
      </div>

      {hist && (
        <div className="panel">
          <h3>Historial</h3>
          <ol className="linea-tiempo">
            {hist.linea_de_tiempo.map((e, i) => (
              <li key={i} className={`evento evento-${e.tipo}`}>
                <span className="evento-tipo">{ICONO_EVENTO[e.tipo]}</span>
                <div><strong>{e.titulo}</strong><p className="ayuda">{fechaHora(e.fecha_hora)} · {e.usuario || "sistema"}{e.detalle ? ` · ${e.detalle}` : ""}</p></div>
              </li>
            ))}
          </ol>
          {hist.ver_auditoria && hist.auditoria.length > 0 && (
            <details>
              <summary>Auditoría completa ({hist.auditoria.length} registros)</summary>
              <div className="tabla-scroll">
                <table>
                  <thead><tr><th>Fecha</th><th>Usuario</th><th>Registro</th><th>Cambios</th><th>Motivo</th></tr></thead>
                  <tbody>{hist.auditoria.map((a, i) => (
                    <tr key={i}><td>{fechaHora(a.fecha_hora)}</td><td>{a.usuario}</td><td>{a.modelo} #{a.objeto_id} · {a.accion}</td>
                      <td>{a.cambios.map((c) => <div key={c.campo}>{c.etiqueta}: {String(c.antes)} → {String(c.despues)}</div>)}</td><td>{a.motivo}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export function RevisionGestion({ g, onDecidir }) {
  const [texto, setTexto] = useState(g.mensaje);
  return (
    <div className="revision">
      <Campo id={`rev-${g.id}`} label="Mensaje que se comunicará al cliente">
        <textarea id={`rev-${g.id}`} rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} />
      </Campo>
      <div className="acciones">
        <button type="button" onClick={() => onDecidir(g, "aprobada")}>Aprobar tal cual</button>
        <button type="button" className="secundario" disabled={texto === g.mensaje || !texto.trim()} onClick={() => onDecidir(g, "modificada", texto)}>Aprobar con este mensaje</button>
      </div>
    </div>
  );
}
