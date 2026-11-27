import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import Estado from "../../components/Estado.jsx";
import { Campo } from "../../components/Formulario.jsx";
import { fecha, monto } from "../../format.js";
import FacturaDetalle from "./FacturaDetalle.jsx";
import FacturaForm from "./FacturaForm.jsx";

const ESTADOS = [["", "Todos"], ["pendiente", "Pendiente"], ["pagada_parcial", "Pagada parcialmente"], ["vencida", "Vencida"],
  ["vencida_pago_parcial", "Vencida con pago parcial"], ["pagada", "Pagada"], ["anulada", "Anulada"]];

export default function Facturas({ usuario }) {
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("");
  const [lista, setLista] = useState([]);
  const [total, setTotal] = useState(0);
  const [sel, setSel] = useState(null);
  const [cargando, setCargando] = useState(false);

  function cargar() {
    setCargando(true);
    api("/facturacion/facturas/", { query: { q, estado } })
      .then((r) => { setLista(r.results); setTotal(r.count); }).catch(() => {}).finally(() => setCargando(false));
  }
  useEffect(() => { const t = setTimeout(cargar, 250); return () => clearTimeout(t); }, [q, estado]);

  return (
    <section className="pagina">
      <div className="pagina-cabecera">
        <div><p className="eyebrow">Registro interno</p><h1>Facturas</h1></div>
        {usuario.es_tesorero && <button type="button" onClick={() => setSel("nueva")}>Cargar factura</button>}
      </div>
      <div className="dos-columnas">
        <div className="panel buscador">
          <div className="filtros">
            <Campo id="fq" label="Buscar"><input id="fq" type="search" placeholder="Número, cliente o RUC" value={q} onChange={(e) => setQ(e.target.value)} /></Campo>
            <Campo id="fe" label="Estado"><select id="fe" value={estado} onChange={(e) => setEstado(e.target.value)}>{ESTADOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Campo>
          </div>
          <p className="ayuda">{cargando ? "Buscando…" : `${total} factura(s)`}</p>
          <ul className="resultados">
            {lista.map((f) => (
              <li key={f.id}>
                <button type="button" className={"fila" + (sel === f.id ? " activa" : "")} onClick={() => setSel(f.id)}>
                  <span className="fila-top"><span className="mono">{f.numero_completo}</span><Estado estado={f.estado} /></span>
                  <span className="fila-cliente">{f.cliente_razon_social}</span>
                  <span className="fila-datos"><span>Vence {fecha(f.fecha_vencimiento)}</span><strong className="num">{monto(f.saldo, f.moneda)}</strong></span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        {sel === "nueva" && <FacturaForm onCreada={(f) => { setSel(f.id); cargar(); }} onCancelar={() => setSel(null)} />}
        {typeof sel === "number" && <FacturaDetalle id={sel} usuario={usuario} onCambio={cargar} />}
        {sel === null && <div className="panel vacio"><h2>Ficha de factura</h2>
          <p>Elija una factura para ver su detalle, el historial de gestiones de cobro y quién cambió su estado o vencimiento{usuario.es_tesorero ? ", o cargue una factura emitida" : ""}.</p></div>}
      </div>
    </section>
  );
}
