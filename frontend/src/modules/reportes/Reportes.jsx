import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import Estado from "../../components/Estado.jsx";
import { fecha, hoyISO, monto } from "../../format.js";

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

function useCarga(path, query, activo = true) {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  const clave = JSON.stringify([path, query]);
  useEffect(() => {
    if (!activo) return;
    setDatos(null);
    setError("");
    api(path, { query }).then(setDatos).catch((e) => setError(e.message));
  }, [clave, activo]);
  return [datos, error];
}

function urlCsv(path, query) {
  const qs = new URLSearchParams({ ...Object.fromEntries(Object.entries(query).filter(([, v]) => v)), formato: "csv" });
  return `/api${path}?${qs}`;
}

function EstadoCuenta() {
  const [q, setQ] = useState("");
  const [clientes, setClientes] = useState([]);
  const [cliente, setCliente] = useState(null);
  const hoy = hoyISO();
  const [desde, setDesde] = useState(`${hoy.slice(0, 4)}-01-01`);
  const [hasta, setHasta] = useState(hoy);
  const query = { desde, hasta };
  const path = cliente ? `/reportes/estado-cuenta/${cliente.id}/` : "";
  const [datos, error] = useCarga(path, query, Boolean(cliente));

  useEffect(() => {
    const t = setTimeout(() => api("/clientes/", { query: { q } }).then((r) => setClientes(r.results || [])).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="reporte">
      <div className="filtros">
        <div className="campo">
          <label htmlFor="cli">Cliente</label>
          <input id="cli" list="lista-clientes" placeholder="Razón social o RUC" value={q}
                 onChange={(e) => {
                   setQ(e.target.value);
                   const c = clientes.find((x) => `${x.razon_social} · ${x.ruc || "sin RUC"}` === e.target.value);
                   if (c) setCliente(c);
                 }} />
          <datalist id="lista-clientes">
            {clientes.map((c) => <option key={c.id} value={`${c.razon_social} · ${c.ruc || "sin RUC"}`} />)}
          </datalist>
        </div>
        <div className="campo"><label htmlFor="desde">Desde</label><input id="desde" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></div>
        <div className="campo"><label htmlFor="hasta">Hasta</label><input id="hasta" type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></div>
        {cliente && <a className="boton-secundario" href={urlCsv(path, query)}>Descargar CSV</a>}
      </div>
      {!cliente && <p className="ayuda">Elija un cliente para ver su estado de cuenta.</p>}
      {error && <p className="msg msg-error">{error}</p>}
      {datos && (
        <>
          <div className="panel ficha">
            <h2>{datos.cliente.razon_social}</h2>
            <p className="ayuda">{datos.cliente.tipo} · RUC {datos.cliente.ruc || "—"} · {datos.cliente.condicion_pago}
              {datos.cliente.plazo_dias ? ` ${datos.cliente.plazo_dias} días` : ""} · Límite {monto(datos.cliente.limite_credito, "PYG")}</p>
            <p className="ayuda">Período {fecha(datos.desde)} al {fecha(datos.hasta)}</p>
          </div>
          {Object.keys(datos.monedas).length === 0 && <p className="ayuda">Sin movimientos en el período.</p>}
          {Object.entries(datos.monedas).map(([m, d]) => (
            <div key={m} className="panel">
              <h3>Movimientos en {m === "PYG" ? "guaraníes" : "dólares"}</h3>
              <div className="tabla-scroll">
                <table>
                  <thead><tr><th>Fecha</th><th>Tipo</th><th>Factura</th><th>Detalle</th><th className="der">Debe</th><th className="der">Haber</th><th className="der">Saldo</th></tr></thead>
                  <tbody>
                    <tr className="fila-suave"><td>{fecha(datos.desde)}</td><td colSpan={5}>Saldo inicial</td><td className="der num">{monto(d.saldo_inicial, m)}</td></tr>
                    {d.movimientos.map((x, i) => (
                      <tr key={i}>
                        <td>{fecha(x.fecha)}</td><td>{x.tipo}</td><td className="mono">{x.documento}</td><td>{x.detalle}</td>
                        <td className="der num">{Number(x.debe) ? monto(x.debe, m) : ""}</td>
                        <td className="der num">{Number(x.haber) ? monto(x.haber, m) : ""}</td>
                        <td className="der num">{monto(x.saldo, m)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot><tr><td colSpan={4}>Totales del período</td><td className="der num">{monto(d.total_debe, m)}</td><td className="der num">{monto(d.total_haber, m)}</td><td className="der num">{monto(d.saldo_final, m)}</td></tr></tfoot>
                </table>
              </div>
            </div>
          ))}
          {datos.facturas_pendientes.length > 0 && (
            <div className="panel">
              <h3>Facturas pendientes al {fecha(datos.hasta)}</h3>
              <div className="tabla-scroll">
                <table>
                  <thead><tr><th>Factura</th><th>Vence</th><th className="der">Días de atraso</th><th className="der">Saldo</th><th className="der">Interés por mora</th><th className="der">Total con interés</th><th>Estado</th></tr></thead>
                  <tbody>
                    {datos.facturas_pendientes.map((f) => (
                      <tr key={f.factura_id}>
                        <td className="mono">{f.numero}</td><td>{fecha(f.fecha_vencimiento)}</td><td className="der num">{f.dias_atraso}</td>
                        <td className="der num">{monto(f.saldo, f.moneda)}</td><td className="der num">{monto(f.interes_mora, f.moneda)}</td>
                        <td className="der num">{monto(f.total_con_interes, f.moneda)}</td><td><Estado estado={f.estado} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Iva() {
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const query = { anio, mes };
  const [datos, error] = useCarga("/reportes/iva/", query);
  const anios = Array.from({ length: 5 }, (_, i) => hoy.getFullYear() - i);
  return (
    <div className="reporte">
      <div className="filtros">
        <div className="campo"><label htmlFor="mes">Mes</label>
          <select id="mes" value={mes} onChange={(e) => setMes(Number(e.target.value))}>{MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select></div>
        <div className="campo"><label htmlFor="anio">Año</label>
          <select id="anio" value={anio} onChange={(e) => setAnio(Number(e.target.value))}>{anios.map((a) => <option key={a}>{a}</option>)}</select></div>
        <a className="boton-secundario" href={urlCsv("/reportes/iva/", query)}>Descargar CSV</a>
      </div>
      {error && <p className="msg msg-error">{error}</p>}
      {datos && (
        <>
          <div className="kpis">
            <div className="panel kpi"><dl>
              <div className="kpi-principal"><dt>Débito fiscal IVA 10%</dt><dd className="num">{monto(datos.totales_gs.debito_fiscal, "PYG")}</dd></div>
              <div><dt>Base imponible</dt><dd className="num">{monto(datos.totales_gs.base_imponible, "PYG")}</dd></div>
              <div><dt>Total facturado</dt><dd className="num">{monto(datos.totales_gs.total, "PYG")}</dd></div>
              <div><dt>Retenciones de IVA</dt><dd className="num">{monto(datos.totales_gs.retencion_iva, "PYG")}</dd></div>
              <div><dt>Facturas</dt><dd className="num">{datos.cantidad_facturas}</dd></div>
            </dl></div>
          </div>
          <p className="ayuda">Período {datos.periodo}. Facturas en USD convertidas con el tipo de cambio de cada factura.
            {datos.sin_aprobacion_sifen ? ` ${datos.sin_aprobacion_sifen} factura(s) aún sin aprobación SIFEN.` : ""}</p>
          {datos.excluidas_sifen.length > 0 && (
            <p className="msg msg-aviso">No suman por estar rechazadas o canceladas en SIFEN: {datos.excluidas_sifen.map((f) => f.numero).join(", ")}.</p>
          )}
          <div className="panel tabla-scroll">
            <table>
              <thead><tr><th>Fecha</th><th>Factura</th><th>Cliente</th><th>RUC</th><th>Moneda</th><th className="der">Base Gs.</th><th className="der">IVA Gs.</th><th className="der">Total Gs.</th><th>SIFEN</th></tr></thead>
              <tbody>
                {datos.facturas.map((f) => (
                  <tr key={f.numero}>
                    <td>{fecha(f.fecha)}</td><td className="mono">{f.numero}</td><td>{f.cliente}</td><td>{f.ruc || "—"}</td>
                    <td>{f.moneda}{f.moneda === "USD" ? ` (TC ${Number(f.tipo_cambio).toLocaleString("es-PY")})` : ""}</td>
                    <td className="der num">{monto(f.base_imponible_gs, "PYG")}</td><td className="der num">{monto(f.iva_gs, "PYG")}</td>
                    <td className="der num">{monto(f.total_gs, "PYG")}</td><td>{f.estado_sifen}</td>
                  </tr>
                ))}
                {datos.facturas.length === 0 && <tr><td colSpan={9} className="ayuda">Sin facturas en el período.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function OcPendientes() {
  const [datos, error] = useCarga("/reportes/oc-pendientes/", {});
  return (
    <div className="reporte">
      <div className="filtros"><a className="boton-secundario" href={urlCsv("/reportes/oc-pendientes/", {})}>Descargar CSV</a></div>
      {error && <p className="msg msg-error">{error}</p>}
      {datos && (
        <>
          <div className="panel">
            <h3>Facturas con OC pendientes de conciliación</h3>
            <p className="ayuda">Facturas vinculadas a una orden de compra que todavía tienen saldo por cobrar.
              Total: {Object.entries(datos.totales_facturas).filter(([, v]) => Number(v)).map(([m, v]) => monto(v, m)).join(" · ") || "—"}</p>
            <div className="tabla-scroll">
              <table>
                <thead><tr><th>OC</th><th>Obra</th><th>Factura</th><th>Cliente</th><th>Vence</th><th className="der">Días de atraso</th><th className="der">Total</th><th className="der">Cobrado</th><th className="der">Saldo</th><th>Estado</th></tr></thead>
                <tbody>
                  {datos.facturas_con_saldo.map((f) => (
                    <tr key={f.factura_id}>
                      <td className="mono">{f.oc}</td><td>{f.obra || "—"}</td><td className="mono">{f.factura}</td><td>{f.cliente}</td>
                      <td>{fecha(f.fecha_vencimiento)}</td><td className="der num">{f.dias_atraso}</td>
                      <td className="der num">{monto(f.total, f.moneda)}</td><td className="der num">{monto(f.cobrado, f.moneda)}</td>
                      <td className="der num">{monto(f.saldo, f.moneda)}</td><td><Estado estado={f.estado} /></td>
                    </tr>
                  ))}
                  {datos.facturas_con_saldo.length === 0 && <tr><td colSpan={10} className="ayuda">No hay facturas con OC pendientes.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
          <div className="panel">
            <h3>Órdenes de compra con monto sin facturar</h3>
            <div className="tabla-scroll">
              <table>
                <thead><tr><th>OC</th><th>Cliente</th><th>Obra</th><th>Fecha</th><th className="der">Monto OC</th><th className="der">Facturado</th><th className="der">Pendiente de facturar</th></tr></thead>
                <tbody>
                  {datos.ordenes_pendientes_de_facturar.map((o) => (
                    <tr key={o.oc + o.cliente}>
                      <td className="mono">{o.oc}</td><td>{o.cliente}</td><td>{o.obra || "—"}</td><td>{fecha(o.fecha)}</td>
                      <td className="der num">{monto(o.monto_oc, o.moneda)}</td><td className="der num">{monto(o.facturado, o.moneda)}</td>
                      <td className="der num">{monto(o.pendiente_de_facturar, o.moneda)}</td>
                    </tr>
                  ))}
                  {datos.ordenes_pendientes_de_facturar.length === 0 && <tr><td colSpan={7} className="ayuda">Todas las OC están facturadas.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

const REPORTES = [
  ["estado-cuenta", "Estado de cuenta", EstadoCuenta],
  ["iva", "IVA por período", Iva],
  ["oc", "OC pendientes", OcPendientes],
];

export default function Reportes() {
  const [actual, setActual] = useState("estado-cuenta");
  const Comp = REPORTES.find(([k]) => k === actual)[2];
  return (
    <section className="pagina">
      <div className="pagina-cabecera">
        <div><p className="eyebrow">Tesorería</p><h1>Reportes</h1></div>
        <div className="segmentado" role="tablist" aria-label="Reporte">
          {REPORTES.map(([k, t]) => (
            <button key={k} type="button" role="tab" aria-selected={actual === k} className={actual === k ? "activo" : ""}
                    onClick={() => setActual(k)}>{t}</button>
          ))}
        </div>
      </div>
      <Comp />
    </section>
  );
}
