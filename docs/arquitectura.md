# Arquitectura y plan de etapas

## Módulos (apps Django)

| App | Responsabilidad | Entidades previstas |
|---|---|---|
| `core` | Usuarios y roles (administrador, tesorero, cobrador), bitácora de auditoría | `Usuario`, `AuditLog` |
| `clientes` | Ficha de cliente: RUC con dígito verificador, tipo (particular / profesional / pyme), condición de pago, plazo y límite de crédito, contacto de cobranza | `Cliente` |
| `facturacion` | Facturas con base / IVA 10% / total, estados, datos SIFEN (CDC, timbrado, estado del DTE), OC opcional para profesionales y pymes, prohibida para particulares | `Factura`, `ItemFactura`, `OrdenCompra` |
| `cobranzas` | Cobro al contado, pagos (uno por factura) totales o parciales, historial de gestiones y promesas de pago con reglas de cobranza no intimidatoria, alertas, cuenta corriente | `Pago`, `GestionCobro`, `ParametrosCobranza`, `Feriado` |
| `intereses` | Tabla paramétrica de tasas máximas del BCP por mes y moneda, cálculo de mora y punitorio (Art. 475 CC, Art. 44 Ley 489/95), simulador | `TasaReferenciaBCP`, `ConfiguracionIntereses` |
| `tesoreria` | DSO, aging (corriente, 1-30, 31-60, 61-90, 90+), proyección de flujo de caja, alertas de vencimiento; siempre separado por moneda | (sin modelos propios) |
| `reportes` | Estado de cuenta, morosidad, IVA débito fiscal por período, OC pendientes de conciliación | (sin modelos propios) |

Dependencias entre módulos: `core` ← `clientes` ← `facturacion` ← `cobranzas`;
`intereses` lee `facturacion` y `cobranzas`; `tesoreria` y `reportes` sólo leen.

## Convenciones

- Montos siempre `Decimal` / `NUMERIC`; PYG sin decimales, USD con 2; redondeo una sola vez al final.
- Nunca se suman PYG y USD sin conversión explícita con tipo de cambio.
- Lógica de negocio en `services.py` de cada app; vistas y serializers finos.
- Ninguna tasa legal hardcodeada: todo parámetro legal es configurable y auditado.

## Plan de etapas

1. ✅ **Esqueleto**: estructura, entornos, Docker, health check.
2. ✅ **Roles, auditoría, clientes y facturación**: permisos por rol, bitácora
   inmutable, tipos de cliente, OC opcional (prohibida para particulares), IVA 10% con validación contra
   doble imposición, límite de crédito, campos SIFEN.
3. ✅ **Factura (ajustes) y cobranzas**: base / IVA 10% exacto / total,
   estados pendiente · pagada_parcial · pagada · vencida, cobro al contado,
   pagos parciales, gestiones de cobro no intimidatorias,
   promesas de pago, alertas y cuenta corriente.
4. ✅ **Pagos y pantalla "Registrar cobranza"**: pago de una factura con
   paso a pagada_parcial / pagada, estado "vencida y en proceso de pago
   parcial", cálculo del saldo pendiente, buscador por cliente o número,
   gestiones de cobro con alertas y revisión de tesorería, datos demo.
5. **Intereses por mora**: tasas BCP, motor de cálculo, simulador.
6. **Tesorería y reportes**: DSO, aging, flujo de caja, IVA por período, morosidad.
7. **Frontend** por módulo e **integración SIFEN** real.
