import { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { Campo, Mensaje } from "../../components/Formulario.jsx";

const ROLES = [["administrador", "Administrador"], ["tesorero", "Tesorero"], ["cobrador", "Cobrador"]];
const NUEVO = { username: "", first_name: "", last_name: "", email: "", rol: "cobrador", password: "" };

export default function Usuarios({ usuario }) {
  const [lista, setLista] = useState([]);
  const [nuevo, setNuevo] = useState(NUEVO);
  const [msg, setMsg] = useState({});
  const cargar = () => api("/core/usuarios/").then((r) => setLista(r.results)).catch((e) => setMsg({ error: e.message }));
  useEffect(() => { cargar(); }, []);

  async function crear(e) {
    e.preventDefault();
    try { await api("/core/usuarios/", { method: "POST", body: nuevo }); setNuevo(NUEVO); setMsg({ ok: "Usuario creado." }); cargar(); }
    catch (err) { setMsg({ error: err.message }); }
  }
  async function cambiar(u, datos) {
    try { await api(`/core/usuarios/${u.id}/`, { method: "PATCH", body: datos }); setMsg({ ok: `Usuario ${u.username} actualizado (queda en la auditoría).` }); cargar(); }
    catch (err) { setMsg({ error: err.message }); }
  }
  const nv = (k) => (e) => setNuevo((v) => ({ ...v, [k]: e.target.value }));

  return (
    <section className="pagina">
      <div className="pagina-cabecera"><div><p className="eyebrow">Administración</p><h1>Usuarios y roles</h1></div></div>
      <Mensaje error={msg.error} ok={msg.ok} />
      <div className="panel tabla-scroll">
        <table>
          <thead><tr><th>Usuario</th><th>Nombre</th><th>Correo</th><th>Rol</th><th>Acceso</th><th>Último ingreso</th></tr></thead>
          <tbody>{lista.map((u) => (
            <tr key={u.id}>
              <td className="mono">{u.username}</td><td>{[u.first_name, u.last_name].join(" ")}</td><td>{u.email}</td>
              <td><select aria-label={`Rol de ${u.username}`} value={u.rol} disabled={u.id === usuario.id} onChange={(e) => cambiar(u, { rol: e.target.value })}>
                {ROLES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></td>
              <td><label className="check"><input type="checkbox" checked={u.is_active} disabled={u.id === usuario.id} onChange={(e) => cambiar(u, { is_active: e.target.checked })} /> Activo</label></td>
              <td>{u.last_login ? new Date(u.last_login).toLocaleString("es-PY", { dateStyle: "short", timeStyle: "short" }) : "—"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <form className="panel" onSubmit={crear}>
        <h2>Nuevo usuario</h2>
        <div className="grilla">
          <Campo id="u-user" label="Usuario"><input id="u-user" value={nuevo.username} onChange={nv("username")} required autoComplete="off" /></Campo>
          <Campo id="u-nom" label="Nombre"><input id="u-nom" value={nuevo.first_name} onChange={nv("first_name")} /></Campo>
          <Campo id="u-ape" label="Apellido"><input id="u-ape" value={nuevo.last_name} onChange={nv("last_name")} /></Campo>
          <Campo id="u-mail" label="Correo"><input id="u-mail" type="email" value={nuevo.email} onChange={nv("email")} /></Campo>
          <Campo id="u-rol" label="Rol"><select id="u-rol" value={nuevo.rol} onChange={nv("rol")}>{ROLES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Campo>
          <Campo id="u-pass" label="Contraseña inicial" ayuda="Mínimo 10 caracteres, no sólo números."><input id="u-pass" type="password" autoComplete="new-password" value={nuevo.password} onChange={nv("password")} required /></Campo>
        </div>
        <p className="ayuda">Administrador: todo, incluida la auditoría y los usuarios. Tesorero: clientes, facturas, pagos, prórrogas y revisión de gestiones. Cobrador: consulta y registra gestiones de cobro.</p>
        <div className="acciones"><button type="submit">Crear usuario</button></div>
      </form>
    </section>
  );
}
