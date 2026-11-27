import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client.js";
import { Campo, Mensaje } from "../../components/Formulario.jsx";
import { hoyISO, monto, normalizarMonto } from "../../format.js";

const ITEM = { descripcion: "", unidad: "UNI", cantidad: "1", precio_unitario: "", descuento: "0" };

// Vista previa con la misma regla del backend: base = total × 100/110, IVA = base × 10%.
function previa(items, moneda, incluyeIva) {
  const dec = moneda === "USD" ? 100 : 1;
  const r = (v) => Math.round(v * dec) / dec;
  const suma = items.reduce((t, it) => t + r((Number(it.cantidad) || 0) * (Number(normalizarMonto(it.precio_unitario, moneda)) || 0) - (Number(it.descuento) || 0)), 0);
  if (incluyeIva) { const base = r(suma * 100 / 110); return { base, iva: r(base * 0.1), total: suma }; }
  const iva = r(suma * 0.1);
  return { base: suma, iva, total: suma + iva };
}

export default function FacturaForm({ onCreada, onCancelar }) {
  const [q, setQ] = useState("");
  const [clientes, setClientes] = useState([]);
  const [cliente, setCliente] = useState(null);
  const [ocs, setOcs] = useState([]);
  const [f, setF] = useState({ timbrado: "", establecimiento: "001", punto_expedicion: "001", numero: "", fecha_emision: hoyISO(),
    condicion: "contado", plazo_dias: "", moneda: "PYG", tipo_cambio: "", orden_compra: "", tasa_interes_anual: "0",
    porcentaje_retencion_iva: "0", precios_incluyen_iva: true, cdc: "", estado_sifen: "aprobado", observaciones: "" });
  const [items, setItems] = useState([{ ...ITEM }]);
  const [nuevaOc, setNuevaOc] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => api("/clientes/", { query: { q } }).then((r) => setClientes(r.results)).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    if (!cliente?.requiere_orden_compra) { setOcs([]); return; }
    api("/facturacion/ordenes-compra/", { query: { cliente: cliente.id } }).then((r) => setOcs(r.results.filter((o) => o.estado !== "anulada"))).catch(() => {});
  }, [cliente]);

  const campo = (k) => (e) => setF((v) => ({ ...v, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const campoItem = (i, k) => (e) => setItems((l) => l.map((it, j) => (j === i ? { ...it, [k]: e.target.value } : it)));
  const p = useMemo(() => previa(items, f.moneda, f.precios_incluyen_iva), [items, f.moneda, f.precios_incluyen_iva]);

  function elegirCliente(texto) {
    setQ(texto);
    const c = clientes.find((x) => `${x.razon_social} · ${x.ruc || "sin RUC"}` === texto);
    if (c) {
      setCliente(c);
      setF((v) => ({ ...v, orden_compra: "", condicion: c.condicion_pago === "credito" ? v.condicion : "contado",
                     plazo_dias: c.plazo_dias || "", porcentaje_retencion_iva: c.tipo === "particular" ? "0" : v.porcentaje_retencion_iva }));
    }
  }

  async function crearOc() {
    setError("");
    try {
      const oc = await api("/facturacion/ordenes-compra/", { method: "POST", body: { ...nuevaOc, cliente: cliente.id, moneda: f.moneda,
        monto_total: normalizarMonto(nuevaOc.monto_total, f.moneda) } });
      setOcs((l) => [oc, ...l]); setF((v) => ({ ...v, orden_compra: oc.id })); setNuevaOc(null);
    } catch (e) { setError(e.message); }
  }

  async function guardar(e) {
    e.preventDefault();
    setError("");
    const cuerpo = {
      ...f, cliente: cliente.id, orden_compra: f.orden_compra || null,
      plazo_dias: f.condicion === "credito" ? Number(f.plazo_dias) : 0,
      tipo_cambio: f.moneda === "USD" ? normalizarMonto(f.tipo_cambio, "PYG") : null,
      numero: f.numero.padStart(7, "0"),
      estado_sifen: f.cdc ? f.estado_sifen : "borrador",
      items: items.filter((it) => it.descripcion).map((it) => ({ ...it, precio_unitario: normalizarMonto(it.precio_unitario, f.moneda) })),
    };
    try { onCreada(await api("/facturacion/facturas/", { method: "POST", body: cuerpo })); }
    catch (err) { setError(err.message); }
  }

  return (
    <form className="panel" onSubmit={guardar}>
      <div><p className="eyebrow">Registro interno</p><h2>Cargar factura emitida</h2>
        <p className="ayuda">Copie los datos de la factura emitida por el sistema de facturación. El CRM calcula base, IVA 10% y vencimiento.</p></div>
      <div className="grilla">
        <Campo id="f-cli" label="Cliente" ancho>
          <input id="f-cli" list="f-clientes" value={q} onChange={(e) => elegirCliente(e.target.value)} placeholder="Razón social o RUC" required />
          <datalist id="f-clientes">{clientes.map((c) => <option key={c.id} value={`${c.razon_social} · ${c.ruc || "sin RUC"}`} />)}</datalist>
        </Campo>
        <Campo id="f-tim" label="Timbrado"><input id="f-tim" inputMode="numeric" maxLength={8} value={f.timbrado} onChange={campo("timbrado")} required /></Campo>
        <Campo id="f-num" label="Número" ayuda="Establecimiento - punto - número">
          <div className="numero-factura">
            <input aria-label="Establecimiento" maxLength={3} value={f.establecimiento} onChange={campo("establecimiento")} required />
            <input aria-label="Punto de expedición" maxLength={3} value={f.punto_expedicion} onChange={campo("punto_expedicion")} required />
            <input id="f-num" aria-label="Número" maxLength={7} value={f.numero} onChange={campo("numero")} required />
          </div>
        </Campo>
        <Campo id="f-fecha" label="Fecha de emisión"><input id="f-fecha" type="date" value={f.fecha_emision} onChange={campo("fecha_emision")} required /></Campo>
        <Campo id="f-cond" label="Condición">
          <select id="f-cond" value={f.condicion} onChange={campo("condicion")}>
            <option value="contado">Contado</option>
            <option value="credito" disabled={cliente && cliente.condicion_pago !== "credito"}>Crédito</option>
          </select>
        </Campo>
        {f.condicion === "credito" && (
          <Campo id="f-plazo" label="Plazo (días)" ayuda={cliente ? `Máximo pactado: ${cliente.plazo_dias} días` : ""}>
            <input id="f-plazo" type="number" min="1" max={cliente?.plazo_dias || 90} value={f.plazo_dias} onChange={campo("plazo_dias")} required />
          </Campo>
        )}
        <Campo id="f-mon" label="Moneda"><select id="f-mon" value={f.moneda} onChange={campo("moneda")}><option value="PYG">Guaraníes</option><option value="USD">Dólares</option></select></Campo>
        {f.moneda === "USD" && <Campo id="f-tc" label="Tipo de cambio (Gs. por US$)"><input id="f-tc" inputMode="decimal" value={f.tipo_cambio} onChange={campo("tipo_cambio")} required /></Campo>}
        {cliente?.requiere_orden_compra && (
          <Campo id="f-oc" label="N° de orden de compra (opcional)">
            <div className="fila-input">
              <select id="f-oc" value={f.orden_compra} onChange={campo("orden_compra")}>
                <option value="">Sin OC</option>
                {ocs.filter((o) => o.moneda === f.moneda).map((o) => <option key={o.id} value={o.id}>{o.numero} · saldo {monto(o.saldo_disponible, o.moneda)}</option>)}
              </select>
              <button type="button" className="secundario" onClick={() => setNuevaOc({ numero: "", fecha: f.fecha_emision, monto_total: "", obra_proyecto: "" })}>Nueva OC</button>
            </div>
          </Campo>
        )}
        <Campo id="f-tasa" label="Tasa de interés pactada (% anual)" ayuda="0 = sin interés pactado"><input id="f-tasa" inputMode="decimal" value={f.tasa_interes_anual} onChange={campo("tasa_interes_anual")} /></Campo>
        {cliente && cliente.tipo !== "particular" && <Campo id="f-ret" label="Retención de IVA (%)"><input id="f-ret" inputMode="decimal" value={f.porcentaje_retencion_iva} onChange={campo("porcentaje_retencion_iva")} /></Campo>}
        <Campo id="f-cdc" label="CDC (opcional)" ayuda="44 dígitos del documento electrónico"><input id="f-cdc" inputMode="numeric" maxLength={44} value={f.cdc} onChange={campo("cdc")} /></Campo>
        {f.cdc && <Campo id="f-sif" label="Estado SIFEN"><select id="f-sif" value={f.estado_sifen} onChange={campo("estado_sifen")}>
          <option value="aprobado">Aprobado</option><option value="aprobado_obs">Aprobado con observación</option><option value="enviado">Enviado</option></select></Campo>}
      </div>

      {nuevaOc && (
        <div className="subpanel">
          <h3>Nueva orden de compra de {cliente.razon_social}</h3>
          <div className="grilla">
            <Campo id="oc-num" label="N° de OC"><input id="oc-num" value={nuevaOc.numero} onChange={(e) => setNuevaOc({ ...nuevaOc, numero: e.target.value })} /></Campo>
            <Campo id="oc-fecha" label="Fecha"><input id="oc-fecha" type="date" value={nuevaOc.fecha} onChange={(e) => setNuevaOc({ ...nuevaOc, fecha: e.target.value })} /></Campo>
            <Campo id="oc-monto" label={`Monto (${f.moneda})`}><input id="oc-monto" inputMode="decimal" value={nuevaOc.monto_total} onChange={(e) => setNuevaOc({ ...nuevaOc, monto_total: e.target.value })} /></Campo>
            <Campo id="oc-obra" label="Obra / proyecto"><input id="oc-obra" value={nuevaOc.obra_proyecto} onChange={(e) => setNuevaOc({ ...nuevaOc, obra_proyecto: e.target.value })} /></Campo>
          </div>
          <div className="acciones"><button type="button" onClick={crearOc}>Guardar OC</button><button type="button" className="secundario" onClick={() => setNuevaOc(null)}>Cancelar</button></div>
        </div>
      )}

      <div className="subpanel">
        <div className="cabecera"><h3>Ítems</h3>
          <label className="check"><input type="checkbox" checked={f.precios_incluyen_iva} onChange={campo("precios_incluyen_iva")} /> Los precios incluyen IVA</label></div>
        <div className="tabla-scroll">
          <table className="tabla-items">
            <thead><tr><th>Descripción</th><th>Unidad</th><th>Cantidad</th><th>Precio unitario</th><th>Descuento</th><th></th></tr></thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i}>
                  <td><input aria-label="Descripción" value={it.descripcion} onChange={campoItem(i, "descripcion")} placeholder="Varilla conformada Ø12 mm x 12 m" required={i === 0} /></td>
                  <td><input aria-label="Unidad" value={it.unidad} onChange={campoItem(i, "unidad")} /></td>
                  <td><input aria-label="Cantidad" inputMode="decimal" value={it.cantidad} onChange={campoItem(i, "cantidad")} /></td>
                  <td><input aria-label="Precio unitario" inputMode="decimal" value={it.precio_unitario} onChange={campoItem(i, "precio_unitario")} /></td>
                  <td><input aria-label="Descuento" inputMode="decimal" value={it.descuento} onChange={campoItem(i, "descuento")} /></td>
                  <td>{items.length > 1 && <button type="button" className="link" onClick={() => setItems((l) => l.filter((_, j) => j !== i))}>Quitar</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button type="button" className="secundario" onClick={() => setItems((l) => [...l, { ...ITEM }])}>Agregar ítem</button>
        <dl className="resumen">
          <div><dt>Base imponible</dt><dd className="num">{monto(p.base, f.moneda)}</dd></div>
          <div><dt>IVA 10%</dt><dd className="num">{monto(p.iva, f.moneda)}</dd></div>
          <div className="destacado"><dt>Total</dt><dd className="num">{monto(p.total, f.moneda)}</dd></div>
        </dl>
      </div>
      <Mensaje error={error} />
      <div className="acciones"><button type="submit" disabled={!cliente}>Guardar factura</button><button type="button" className="secundario" onClick={onCancelar}>Cancelar</button></div>
    </form>
  );
}
