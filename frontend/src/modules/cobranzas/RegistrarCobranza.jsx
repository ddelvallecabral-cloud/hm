import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client.js";
import Estado from "../../components/Estado.jsx";
import { centavos, fecha, hoyISO, monto, normalizarMonto } from "../../format.js";

const MEDIOS = [
  ["efectivo", "Efectivo"],
  ["transferencia", "Transferencia / SIPAP"],
  ["cheque", "Cheque al día"],
  ["cheque_diferido", "Cheque diferido"],
  ["tarjeta", "Tarjeta"],
  ["billetera", "Billetera / QR"],
  ["retencion", "Comprobante de retención"],
];
const CON_REFERENCIA = ["transferencia", "cheque", "cheque_diferido"];

function estadoResultante(factura, montoTxt) {
  if (!factura || !montoTxt) return null;
  let pago;
  const limpio = normalizarMonto(montoTxt, factura.moneda);
  if (!/^\d+(\.\d{1,2})?$/.test(limpio)) return null;
  try { pago = centavos(limpio); } catch { return null; }
  const saldo = centavos(factura.saldo);
  if (pago <= 0n) return null;
  if (pago > saldo) return "excede";
  if (pago === saldo) return "pagada";
  return factura.fecha_vencimiento < hoyISO() ? "vencida_pago_parcial" : "pagada_parcial";
}

export default function RegistrarCobranza({ usuario }) {
  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState([]);
  const [buscando, setBuscando] = useState(false);
  const [errorBusqueda, setErrorBusqueda] = useState("");
  const [factura, setFactura] = useState(null);
  const [form, setForm] = useState({ monto: "", fecha: hoyISO(), medio: "efectivo", referencia: "", banco: "", numero_recibo: "" });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");
  const [exito, setExito] = useState(null);
  const temporizador = useRef();
  const puedeCobrar = usuario.es_tesorero;

  async function buscar(texto) {
    setBuscando(true);
    setErrorBusqueda("");
    try {
      setResultados(await api("/cobranzas/facturas-por-cobrar/", { query: { q: texto } }));
    } catch (e) {
      setErrorBusqueda(e.message);
    } finally {
      setBuscando(false);
    }
  }

  useEffect(() => {
    clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => buscar(q), 300);
    return () => clearTimeout(temporizador.current);
  }, [q]);

  function elegir(f) {
    setFactura(f);
    setExito(null);
    setError("");
    setForm((v) => ({ ...v, monto: f.moneda === "USD" ? Number(f.saldo).toFixed(2) : String(Math.round(Number(f.saldo))) }));
  }

  const campo = (k) => (e) => setForm((v) => ({ ...v, [k]: e.target.value }));
  const resultado = useMemo(() => estadoResultante(factura, form.monto), [factura, form.monto]);

  async function registrar(e) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      const r = await api("/cobranzas/registrar-cobranza/", {
        method: "POST", body: { factura: factura.id, ...form, monto: normalizarMonto(form.monto, factura.moneda) },
      });
      setExito(r);
      setFactura(null);
      setForm((v) => ({ ...v, monto: "", referencia: "", banco: "", numero_recibo: "" }));
      buscar(q);
    } catch (err) {
      setError(err.message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="cobranza">
      <div className="panel buscador">
        <label htmlFor="buscar" className="titulo-campo">Buscar factura</label>
        <input id="buscar" type="search" placeholder="Cliente, RUC o número (001-001-0000123 o 123)"
               value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
        <p className="ayuda" aria-live="polite">
          {buscando ? "Buscando…" : errorBusqueda || `${resultados.length} factura(s) con saldo pendiente`}
        </p>
        <ul className="resultados">
          {resultados.map((f) => (
            <li key={f.id}>
              <button type="button" className={"fila" + (factura?.id === f.id ? " activa" : "")} onClick={() => elegir(f)}>
                <span className="fila-top">
                  <span className="mono">{f.numero}</span>
                  <Estado estado={f.estado} />
                </span>
                <span className="fila-cliente">{f.cliente}</span>
                <span className="fila-datos">
                  <span>Vence {fecha(f.fecha_vencimiento)}</span>
                  <strong className="num">{monto(f.saldo, f.moneda)}</strong>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="detalle">
        {exito && (
          <div className="panel exito" role="status">
            <h2>Cobranza registrada</h2>
            <p>
              Pago #{exito.pago.id} por <strong>{monto(exito.pago.monto, exito.pago.moneda)}</strong> aplicado a la
              factura <span className="mono">{exito.factura.numero}</span> de {exito.factura.cliente}.
            </p>
            <p>
              Saldo pendiente: <strong className="num">{monto(exito.factura.saldo, exito.factura.moneda)}</strong> ·
              Estado: <Estado estado={exito.factura.estado} />
            </p>
          </div>
        )}

        {!factura && !exito && (
          <div className="panel vacio">
            <h2>Registrar cobranza</h2>
            <p>Busque la factura por cliente, RUC o número y selecciónela para cargar el pago.
              Un pago menor al saldo deja la factura pagada parcialmente; el pago del saldo completo la deja pagada.</p>
          </div>
        )}

        {factura && (
          <form className="panel" onSubmit={registrar}>
            <div className="cabecera">
              <div>
                <p className="eyebrow">Factura {factura.condicion === "credito" ? "a crédito" : "al contado"}</p>
                <h2 className="mono">{factura.numero}</h2>
                <p>{factura.cliente}{factura.ruc ? ` · RUC ${factura.ruc}` : ""}</p>
              </div>
              <Estado estado={factura.estado} />
            </div>
            <dl className="resumen">
              <div><dt>Emisión</dt><dd>{fecha(factura.fecha_emision)}</dd></div>
              <div><dt>Vencimiento</dt><dd>{fecha(factura.fecha_vencimiento)}</dd></div>
              <div><dt>Total</dt><dd className="num">{monto(factura.total, factura.moneda)}</dd></div>
              <div><dt>Cobrado</dt><dd className="num">{monto(factura.cobrado, factura.moneda)}</dd></div>
              <div className="destacado"><dt>Saldo pendiente</dt><dd className="num">{monto(factura.saldo, factura.moneda)}</dd></div>
            </dl>

            {!puedeCobrar && (
              <p className="msg msg-aviso">Su rol ({usuario.rol}) puede consultar, pero sólo tesorería registra pagos.</p>
            )}

            <fieldset disabled={!puedeCobrar || enviando}>
              <div className="grilla">
                <div className="campo">
                  <label htmlFor="monto">Monto ({factura.moneda})</label>
                  <input id="monto" inputMode="decimal" value={form.monto} onChange={campo("monto")} required />
                  <span className="ayuda">
                    {resultado === "excede" ? "Supera el saldo pendiente." :
                     resultado ? <>La factura quedará: <Estado estado={resultado} /></> : "Ingrese el monto cobrado."}
                  </span>
                </div>
                <div className="campo">
                  <label htmlFor="fecha">Fecha del cobro</label>
                  <input id="fecha" type="date" value={form.fecha} onChange={campo("fecha")} required />
                </div>
                <div className="campo">
                  <label htmlFor="medio">Medio de pago</label>
                  <select id="medio" value={form.medio} onChange={campo("medio")}>
                    {MEDIOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                  </select>
                </div>
                <div className="campo">
                  <label htmlFor="referencia">N° de referencia {CON_REFERENCIA.includes(form.medio) ? "(obligatorio)" : "(opcional)"}</label>
                  <input id="referencia" value={form.referencia} onChange={campo("referencia")}
                         required={CON_REFERENCIA.includes(form.medio)} placeholder="Transferencia, cheque o comprobante" />
                </div>
                <div className="campo">
                  <label htmlFor="banco">Banco</label>
                  <input id="banco" value={form.banco} onChange={campo("banco")} />
                </div>
                <div className="campo">
                  <label htmlFor="recibo">N° de recibo</label>
                  <input id="recibo" value={form.numero_recibo} onChange={campo("numero_recibo")} />
                </div>
              </div>
              {error && <p className="msg msg-error" role="alert">{error}</p>}
              <div className="acciones">
                <button type="submit" disabled={resultado === "excede" || !resultado}>
                  {enviando ? "Registrando…" : "Registrar cobranza"}
                </button>
                <button type="button" className="secundario" onClick={() => setFactura(null)}>Cancelar</button>
              </div>
            </fieldset>
          </form>
        )}
      </div>
    </section>
  );
}
