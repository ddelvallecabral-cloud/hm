// Formato paraguayo: Gs. sin decimales con punto de miles; USD con 2 decimales.
export function monto(valor, moneda) {
  const n = Number(valor || 0);
  const dec = moneda === "USD" ? 2 : 0;
  const txt = n.toLocaleString("es-PY", { minimumFractionDigits: dec, maximumFractionDigits: dec });
  return moneda === "USD" ? `US$ ${txt}` : `Gs. ${txt}`;
}

export function fecha(iso) {
  if (!iso) return "";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export function hoyISO() {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

// Compara montos como decimales exactos (texto con 2 decimales) para evitar errores de float.
export function centavos(valor) {
  const [ent, dec = ""] = String(valor ?? "0").replace(/\s/g, "").split(".");
  return BigInt(ent || "0") * 100n + BigInt((dec + "00").slice(0, 2));
}

export const ESTADOS = {
  pendiente: { texto: "Pendiente", tono: "neutro" },
  pagada_parcial: { texto: "Pagada parcialmente", tono: "aviso" },
  pagada: { texto: "Pagada", tono: "ok" },
  vencida: { texto: "Vencida", tono: "alerta" },
  vencida_pago_parcial: { texto: "Vencida y en proceso de pago parcial", tono: "alerta" },
  anulada: { texto: "Anulada", tono: "neutro" },
};

// Acepta "4.000.000" o "4000000" en guaraníes y "1.234,56" o "1234.56" en dólares; devuelve "4000000" / "1234.56".
export function normalizarMonto(texto, moneda) {
  let t = String(texto || "").replace(/\s|Gs\.?|US\$/gi, "");
  if (moneda === "PYG") return t.replace(/[.,]/g, "");
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  return t;
}
