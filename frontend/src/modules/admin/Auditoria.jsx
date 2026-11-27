import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { Campo, Mensaje } from "../../components/Formulario.jsx";

const MODELOS = [["", "Todos"], ["facturacion.Factura", "Facturas"], ["cobranzas.Pago", "Pagos"], ["clientes.Cliente", "Clientes"],
  ["cobranzas.GestionCobro", "Gestiones de cobro"], ["core.Usuario", "Usuarios"], ["intereses.TasaReferenciaBCP", "Tasas BCP"],
  ["facturacion.OrdenCompra", "Órdenes de compra"]];
const CAMPOS = [["", "Cualquier cambio"], ["estado", "Estado de factura"], ["fecha_vencimiento", "Vencimiento"], ["anulado", "Anulación de pago"],
  ["saldo", "Saldo"], ["rol", "Rol de usuario"], ["limite_credito", "Límite de crédito"], ["tasa_maxima_anual", "Tasa BCP"]];

export default function Auditoria() {
  const [f, setF] = useState({ modelo: "facturacion.Factura", campo: "", usuario: "", desde: "", hasta: "" });
  const [datos, setDatos] = useState(null);
  const [pagina, setPagina] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/core/auditoria/", { query: { ...f, page: pagina } }).then(setDatos).catch((e) => setError(e.message));
  }, [JSON.stringify(f), pagina]);
  const campo = (k) => (e) => { setPagina(1); setF((v) => ({ ...v, [k]: e.target.value })); };

  return (
    <section className="pagina">
      <div className="pagina-cabecera"><div><p className="eyebrow">Administración</p><h1>Auditoría</h1></div></div>
      <p className="ayuda">Quién cambió qué y cuándo. Los registros no se pueden editar ni borrar.</p>
      <div className="panel filtros">
        <Campo id="au-m" label="Registro"><select id="au-m" value={f.modelo} onChange={campo("modelo")}>{MODELOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Campo>
        <Campo id="au-c" label="Campo modificado"><select id="au-c" value={f.campo} onChange={campo("campo")}>{CAMPOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Campo>
        <Campo id="au-u" label="Usuario"><input id="au-u" value={f.usuario} onChange={campo("usuario")} /></Campo>
        <Campo id="au-d" label="Desde"><input id="au-d" type="date" value={f.desde} onChange={campo("desde")} /></Campo>
        <Campo id="au-h" label="Hasta"><input id="au-h" type="date" value={f.hasta} onChange={campo("hasta")} /></Campo>
      </div>
      <Mensaje error={error} />
      {datos && (
        <div className="panel">
          <p className="ayuda">{datos.count} registro(s)</p>
          <div className="tabla-scroll">
            <table>
              <thead><tr><th>Fecha y hora</th><th>Usuario</th><th>Acción</th><th>Registro</th><th>Cambios</th><th>Motivo</th><th>IP</th></tr></thead>
              <tbody>{datos.results.map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.fecha_hora).toLocaleString("es-PY", { dateStyle: "short", timeStyle: "medium" })}</td>
                  <td>{a.usuario_nombre || "sistema"}</td><td>{a.accion}</td><td>{a.objeto_repr || `${a.modelo} #${a.objeto_id}`}</td>
                  <td>{Object.entries(a.cambios).filter(([k]) => !f.campo || k === f.campo).slice(0, 6).map(([k, [antes, despues]]) => (
                    <div key={k}><span className="mono">{k}</span>: {String(antes ?? "—")} → {String(despues ?? "—")}</div>))}</td>
                  <td>{a.motivo}</td><td className="mono">{a.ip || ""}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="acciones">
            <button type="button" className="secundario" disabled={!datos.previous} onClick={() => setPagina((p) => p - 1)}>Anterior</button>
            <button type="button" className="secundario" disabled={!datos.next} onClick={() => setPagina((p) => p + 1)}>Siguiente</button>
          </div>
        </div>
      )}
    </section>
  );
}
