import { useState } from "react";
import { api, prepararCsrf } from "../api/client.js";

export default function Login({ onIngreso }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function ingresar(e) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      await prepararCsrf();
      onIngreso(await api("/core/login/", { method: "POST", body: { username, password } }));
    } catch (err) {
      setError(err.message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="login">
      <form className="panel login-form" onSubmit={ingresar}>
        <div>
          <p className="eyebrow">Tesorería</p>
          <h1>CRM de cobranzas</h1>
        </div>
        <label htmlFor="usuario">Usuario</label>
        <input id="usuario" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <label htmlFor="clave">Contraseña</label>
        <input id="clave" type="password" autoComplete="current-password" value={password}
               onChange={(e) => setPassword(e.target.value)} required />
        {error && <p className="msg msg-error" role="alert">{error}</p>}
        <button type="submit" disabled={enviando}>{enviando ? "Ingresando…" : "Ingresar"}</button>
      </form>
    </main>
  );
}
