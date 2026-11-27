// Piezas de formulario compartidas.
export function Campo({ id, label, ayuda, children, ancho }) {
  return (
    <div className={"campo" + (ancho ? " campo-ancho" : "")}>
      <label htmlFor={id}>{label}</label>
      {children}
      {ayuda && <span className="ayuda">{ayuda}</span>}
    </div>
  );
}

export function Mensaje({ error, ok }) {
  if (error) return <p className="msg msg-error" role="alert">{error}</p>;
  if (ok) return <p className="msg msg-ok" role="status">{ok}</p>;
  return null;
}

export const TIPOS_CLIENTE = [
  ["particular", "Particular"],
  ["profesional_independiente", "Profesional independiente"],
  ["pyme", "Pyme / Empresa"],
];
