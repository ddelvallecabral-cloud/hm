import { ESTADOS } from "../format.js";

export default function Estado({ estado }) {
  const e = ESTADOS[estado] || { texto: estado, tono: "neutro" };
  return <span className={`estado estado-${e.tono}`}>{e.texto}</span>;
}
