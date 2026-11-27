# Arquitectura y plan de etapas

## Módulos (apps Django)

| App | Responsabilidad | Entidades previstas |
|---|---|---|
| `core` | Usuarios y roles (administrador, tesorero, cobrador), bitácora de auditoría, parámetros globales, utilidades monetarias | `Usuario`, `AuditLog`, `ParametrosTesoreria`, `Feriado` |
| `clientes` | Ficha de cliente: RUC con dígito verificador, tipo (particular / profesional / pyme), condición de pago, plazo y límite de crédito, contacto de cobranza | `Cliente` |
| `facturacion` | Facturas con desglose base/IVA, datos SIFEN (CDC, timbrado, estado del DTE), OC obligatoria sólo para profesionales y pymes | `Factura`, `ItemFactura`, `OrdenCompra` |
| `cobranzas` | Cobro al contado, pagos parciales, imputación capital/intereses, historial de gestiones y promesas de pago con reglas de cobranza no intimidatoria | `Pago`, `AplicacionPago`, `GestionCobro` |
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
   inmutable, tipos de cliente, OC condicional, IVA 10% con validación contra
   doble imposición, límite de crédito, campos SIFEN.
3. **Cobranzas**: cobro al contado, pagos parciales con imputación a capital o
   intereses, gestiones de cobro no intimidatorias, promesas de pago.
4. **Intereses por mora**: tasas BCP, motor de cálculo, simulador.
5. **Tesorería y reportes**: DSO, aging, flujo de caja, IVA por período, morosidad.
6. **Frontend** por módulo e **integración SIFEN** real.
