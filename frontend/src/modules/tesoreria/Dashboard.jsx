import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import Estado from "../../components/Estado.jsx";
import { fecha, hoyISO, monto } from "../../format.js";

const COLORES = { corriente: "var(--aging-0)", "1-30": "var(--aging-1)", "31-60": "var(--aging-2)", "61-90": "var(--aging-3)", "90+": "var(--aging-4)" };
const MONEDAS = [["", "Todas"], ["PYG", "Guaraníes"], ["USD", "Dólares"]];

function BarraAging({ aging, moneda, total }) {
  const t = Number(total);
  if (!t) return <p className="ayuda">Sin cartera en {moneda}.</p>;
  return (
    <div className="barra-aging" role="img"
         aria-label={aging.map((g) => `${g.titulo}: ${monto(g.totales[moneda].saldo, moneda)}`).join(", ")}>
      {aging.map((g) => {
        const v = Number(g.totales[moneda].saldo);
        return v > 0 ? <span key={g.rango} style={{ flexGrow: v, background: COLORES[g.rango] }} title={`${g.titulo}: ${monto(v, moneda)}`} /> : null;
      })}
    </div>
  );
}

export default function Dashboard() {
  const [moneda, setMoneda] = useState("");
  const [corte, setCorte] = useState(hoyISO());
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api("/tesoreria/dashboard/", { query: { moneda, fecha: corte } }).then(setDatos).catch((e) => setError(e.message));
  }, [moneda, corte]);

  const csv = `/api/tesoreria/dashboard/?formato=csv&fecha=${corte}${moneda ? `&moneda=${moneda}` : ""}`;

  return (
    <section className="pagina">
      <div className="pagina-cabecera">
        <div>
          <p className="eyebrow">Tesorería</p>
          <h1>Cartera por cobrar</h1>
        </div>
        <div className="filtros">
          <div className="segmentado" role="group" aria-label="Moneda">
            {MONEDAS.map(([v, t]) => (
              <button key={v} type="button" className={moneda === v ? "activo" : ""} aria-pressed={moneda === v}
                      onClick={() => setMoneda(v)}>{t}</button>
            ))}
          </div>
          <label className="campo-inline" htmlFor="corte">Corte
            <input id="corte" type="date" value={corte} onChange={(e) => setCorte(e.target.value || hoyISO())} />
          </label>
          <a className="boton-secundario" href={csv}>Descargar CSV</a>
        </div>
      </div>

      {error && <p className="msg msg-error">{error}</p>}
      {!datos && !error && <p className="ayuda">Cargando…</p>}
      {datos && (
        <>
          {datos.avisos.map((a) => <p key={a} className="msg msg-aviso">{a}</p>)}
          <div className="kpis">
            {Object.entries(datos.cartera).map(([m, c]) => (
              <article key={m} className="panel kpi">
                <header><h2>{m === "PYG" ? "Guaraníes" : "Dólares"}</h2><span className="ayuda">{c.cantidad} factura(s)</span></header>
                <dl>
                  <div className="kpi-principal"><dt>Total por cobrar</dt><dd className="num">{monto(c.total_por_cobrar, m)}</dd></div>
                  <div><dt>Vencido</dt><dd className="num">{monto(c.vencido, m)}</dd></div>
                  <div><dt>Interés por mora acumulado</dt><dd className="num">{monto(c.interes_mora, m)}</dd></div>
                  <div><dt>DSO</dt><dd className="num">{datos.dso[m].dso ? `${Number(datos.dso[m].dso).toLocaleString("es-PY")} días` : "—"}</dd></div>
                  <div><dt>Cobro real promedio</dt><dd className="num">{datos.dso[m].dias_promedio_cobro_real ? `${Number(datos.dso[m].dias_promedio_cobro_real).toLocaleString("es-PY")} días` : "—"}</dd></div>
                </dl>
                <BarraAging aging={datos.aging} moneda={m} total={c.total_por_cobrar} />
              </article>
            ))}
          </div>
          <p className="ayuda">DSO = cuentas por cobrar a crédito ÷ ventas a crédito de los últimos {datos.dso[Object.keys(datos.dso)[0]].dias_periodo} días × {datos.dso[Object.keys(datos.dso)[0]].dias_periodo}. Cobro real promedio: días entre emisión y pago de los cobros del período.</p>
          <ul className="leyenda">
            {datos.aging.map((g) => <li key={g.rango}><span style={{ background: COLORES[g.rango] }} />{g.titulo}</li>)}
          </ul>

          {datos.aging.map((g) => {
            const cant = g.facturas.length;
            return (
              <details key={g.rango} className="panel grupo" open={cant > 0 && g.rango !== "corriente"}>
                <summary>
                  <span className="grupo-titulo"><span className="punto" style={{ background: COLORES[g.rango] }} />{g.titulo}</span>
                  <span className="grupo-totales">
                    {cant} factura(s)
                    {Object.entries(g.totales).filter(([, t]) => t.cantidad).map(([m, t]) => (
                      <span key={m} className="num"> · {monto(t.saldo, m)}{Number(t.interes_mora) ? ` + ${monto(t.interes_mora, m)} interés` : ""}</span>
                    ))}
                  </span>
                </summary>
                {cant > 0 ? (
                  <div className="tabla-scroll">
                    <table>
                      <thead><tr><th>Factura</th><th>Cliente</th><th>Vence</th><th className="der">Días</th><th className="der">Saldo</th><th className="der">Interés por mora</th><th className="der">Total con interés</th><th>Estado</th></tr></thead>
                      <tbody>
                        {g.facturas.map((f) => (
                          <tr key={f.factura_id}>
                            <td className="mono">{f.numero}</td>
                            <td>{f.cliente}</td>
                            <td>{fecha(f.fecha_vencimiento)}</td>
                            <td className="der num">{f.dias_atraso}</td>
                            <td className="der num">{monto(f.saldo, f.moneda)}</td>
                            <td className="der num" title={f.tasa_mora ? `${f.tasa_mora}% anual` : f.aviso || ""}>{monto(f.interes_mora, f.moneda)}</td>
                            <td className="der num">{monto(f.total_con_interes, f.moneda)}</td>
                            <td><Estado estado={f.estado} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <p className="ayuda">Sin facturas en este tramo.</p>}
              </details>
            );
          })}
        </>
      )}
    </section>
  );
}
