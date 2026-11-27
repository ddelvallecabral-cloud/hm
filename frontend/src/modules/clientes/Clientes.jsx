import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { Campo, Mensaje, TIPOS_CLIENTE } from "../../components/Formulario.jsx";
import { monto } from "../../format.js";

const VACIO = {
  razon_social: "", ruc: "", tipo: "particular", condicion_pago: "contado", plazo_dias: "", limite_credito: "0",
  contacto_cobranza: "", telefono_cobranza: "", email_cobranza: "", direccion: "", ciudad: "",
  acepta_whatsapp: false, activo: true,
};

export default function Clientes({ usuario }) {
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState("");
  const [lista, setLista] = useState([]);
  const [form, setForm] = useState(null); // null = nada abierto; {id?:…} = edición/alta
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const editable = usuario.es_tesorero;

  function cargar() {
    api("/clientes/", { query: { q, tipo } }).then((r) => setLista(r.results)).catch((e) => setError(e.message));
  }
  useEffect(() => { const t = setTimeout(cargar, 250); return () => clearTimeout(t); }, [q, tipo]);

  const campo = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function guardar(e) {
    e.preventDefault();
    setError(""); setOk("");
    const datos = { ...form, plazo_dias: form.condicion_pago === "credito" ? Number(form.plazo_dias) || null : null,
                    limite_credito: form.condicion_pago === "credito" ? String(form.limite_credito).replace(/\./g, "") : "0" };
    try {
      const r = form.id
        ? await api(`/clientes/${form.id}/`, { method: "PATCH", body: { ...datos, motivo } })
        : await api("/clientes/", { method: "POST", body: datos });
      setForm(r); setMotivo(""); setOk(form.id ? "Cliente actualizado." : "Cliente creado.");
      cargar();
    } catch (err) { setError(err.message); }
  }

  return (
    <section className="pagina">
      <div className="pagina-cabecera">
        <div><p className="eyebrow">Maestros</p><h1>Clientes</h1></div>
        {editable && <button type="button" onClick={() => { setForm({ ...VACIO }); setOk(""); setError(""); }}>Nuevo cliente</button>}
      </div>
      <div className="dos-columnas">
        <div className="panel buscador">
          <div className="filtros">
            <Campo id="buscar-cli" label="Buscar"><input id="buscar-cli" type="search" placeholder="Razón social o RUC" value={q} onChange={(e) => setQ(e.target.value)} /></Campo>
            <Campo id="tipo-cli" label="Tipo">
              <select id="tipo-cli" value={tipo} onChange={(e) => setTipo(e.target.value)}>
                <option value="">Todos</option>{TIPOS_CLIENTE.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            </Campo>
          </div>
          <ul className="resultados">
            {lista.map((c) => (
              <li key={c.id}>
                <button type="button" className={"fila" + (form?.id === c.id ? " activa" : "")} onClick={() => { setForm(c); setOk(""); setError(""); }}>
                  <span className="fila-cliente">{c.razon_social}</span>
                  <span className="fila-datos"><span>{c.tipo_display} · {c.ruc || "sin RUC"}</span>
                    <span>{c.condicion_pago === "credito" ? `Crédito ${c.plazo_dias} días` : "Contado"}</span></span>
                </button>
              </li>
            ))}
            {lista.length === 0 && <li className="ayuda">Sin clientes para esa búsqueda.</li>}
          </ul>
        </div>
        <div className="detalle">
          {!form && <div className="panel vacio"><h2>Ficha de cliente</h2><p>Elija un cliente de la lista{editable ? " o cree uno nuevo" : ""}.</p></div>}
          {form && (
            <form className="panel" onSubmit={guardar}>
              <h2>{form.id ? form.razon_social : "Nuevo cliente"}</h2>
              {form.id && <p className="ayuda">{form.requiere_orden_compra ? "Maneja orden de compra (opcional al facturar)." : "Particular: no maneja orden de compra."}</p>}
              <fieldset disabled={!editable}>
                <div className="grilla">
                  <Campo id="c-rs" label="Razón social" ancho><input id="c-rs" value={form.razon_social} onChange={campo("razon_social")} required /></Campo>
                  <Campo id="c-tipo" label="Tipo de cliente">
                    <select id="c-tipo" value={form.tipo} onChange={campo("tipo")}>{TIPOS_CLIENTE.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
                  </Campo>
                  <Campo id="c-ruc" label="RUC" ayuda={form.tipo === "particular" ? "Opcional para particulares. Formato 1234567-8." : "Obligatorio. Formato 80012345-0."}>
                    <input id="c-ruc" value={form.ruc} onChange={campo("ruc")} placeholder="80012345-0" />
                  </Campo>
                  <Campo id="c-cond" label="Condición de pago">
                    <select id="c-cond" value={form.condicion_pago} onChange={campo("condicion_pago")}><option value="contado">Contado</option><option value="credito">Crédito</option></select>
                  </Campo>
                  {form.condicion_pago === "credito" && <>
                    <Campo id="c-plazo" label="Plazo">
                      <select id="c-plazo" value={form.plazo_dias || ""} onChange={campo("plazo_dias")} required>
                        <option value="">Elegir</option>{[30, 60, 90].map((d) => <option key={d} value={d}>{d} días</option>)}
                      </select>
                    </Campo>
                    <Campo id="c-lim" label="Límite de crédito (Gs.)" ayuda={monto(String(form.limite_credito).replace(/\./g, ""), "PYG")}>
                      <input id="c-lim" inputMode="numeric" value={form.limite_credito} onChange={campo("limite_credito")} required />
                    </Campo>
                  </>}
                  <Campo id="c-cont" label="Contacto de cobranza"><input id="c-cont" value={form.contacto_cobranza} onChange={campo("contacto_cobranza")} /></Campo>
                  <Campo id="c-tel" label="Teléfono"><input id="c-tel" value={form.telefono_cobranza} onChange={campo("telefono_cobranza")} /></Campo>
                  <Campo id="c-mail" label="Correo de cobranza"><input id="c-mail" type="email" value={form.email_cobranza} onChange={campo("email_cobranza")} /></Campo>
                  <Campo id="c-dir" label="Dirección"><input id="c-dir" value={form.direccion} onChange={campo("direccion")} /></Campo>
                  <Campo id="c-ciu" label="Ciudad"><input id="c-ciu" value={form.ciudad} onChange={campo("ciudad")} /></Campo>
                </div>
                <label className="check"><input type="checkbox" checked={form.acepta_whatsapp} onChange={campo("acepta_whatsapp")} /> Autorizó contacto por WhatsApp/SMS</label>
                <label className="check"><input type="checkbox" checked={form.activo} onChange={campo("activo")} /> Activo</label>
                {form.id && <Campo id="c-mot" label="Motivo del cambio (queda en la auditoría)"><input id="c-mot" value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>}
                <Mensaje error={error} ok={ok} />
                {editable && <div className="acciones"><button type="submit">{form.id ? "Guardar cambios" : "Crear cliente"}</button>
                  <button type="button" className="secundario" onClick={() => setForm(null)}>Cerrar</button></div>}
              </fieldset>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
