# CRM de Tesorería — Hierro Metal S.R.L.

CRM de **uso interno** del departamento de Tesorería de Hierro Metal S.R.L.
(hierros y productos siderúrgicos, Paraguay): seguimiento de cobranzas al
contado y a crédito, facturas en **PYG** y **USD** con **IVA 10%**, clientes
**particulares / profesionales / pymes** e **intereses por mora** según los
topes del **BCP**.

Las facturas las emite el sistema de facturación electrónica de la empresa; el
CRM las **registra** (con su CDC, timbrado y estado SIFEN como referencia) para
gestionar la cobranza. No emite documentos ni se conecta con la SET.

> **Estado: fase 7** — todas las pantallas (dashboard, facturas, registrar
> cobranza, gestiones, clientes, reportes, tasas BCP, usuarios y auditoría),
> roles, auditoría de cambios, historial de gestiones por factura, intereses
> por mora e identidad visual de la empresa. Ver
> [`docs/arquitectura.md`](docs/arquitectura.md).

## Stack

| Capa          | Tecnología                                         |
|---------------|----------------------------------------------------|
| Backend / API | Python 3.13, Django 5.1, Django REST Framework     |
| Base de datos | PostgreSQL 16 (`NUMERIC` exacto para montos)       |
| Frontend      | React 18 + Vite 6                                  |
| Infra dev     | Docker Compose                                     |
| Producción    | Gunicorn detrás de un proxy HTTPS (Nginx o similar)|

¿Por qué Django? El ORM y el admin dan rápido un back-office multiusuario con
permisos, el manejo de `Decimal` es nativo (crítico para montos e impuestos) y
las migraciones hacen trazables los cambios del esquema.

## Estructura de carpetas

```
.
├── backend/
│   ├── manage.py                  # usa config.settings.dev por defecto
│   ├── Dockerfile
│   ├── .env.example               # variables de entorno documentadas
│   ├── requirements/
│   │   ├── base.txt               # comunes
│   │   ├── dev.txt                # + herramientas de desarrollo
│   │   └── prod.txt               # + gunicorn
│   ├── config/
│   │   ├── env.py                 # lectura tipada de variables (+ .env en dev)
│   │   ├── settings/
│   │   │   ├── base.py            # común: apps, BD, zona horaria, DRF, parámetros del CRM
│   │   │   ├── dev.py             # DEBUG, email a consola, auth básica para probar la API
│   │   │   ├── prod.py            # secretos obligatorios, HTTPS, HSTS, cookies seguras
│   │   │   └── test.py            # tests
│   │   ├── urls.py                # /admin, /api/health, /api/<modulo>/
│   │   ├── wsgi.py / asgi.py      # usan config.settings.prod por defecto
│   └── apps/
│       ├── core/                  # usuarios, roles, auditoría, utilidades monetarias
│       ├── clientes/              # ficha de cliente, RUC, tipo, crédito
│       ├── facturacion/           # facturas, IVA 10%, datos SIFEN de referencia, OC
│       ├── cobranzas/             # pagos, gestiones de cobro
│       ├── intereses/             # tasas BCP, mora y punitorios PYG/USD
│       ├── tesoreria/             # DSO, aging, flujo de caja, alertas
│       └── reportes/              # estado de cuenta, morosidad, IVA, OC
│          (cada app: apps.py, models.py, services.py, urls.py, migrations/, tests/)
├── frontend/
│   ├── .env.example
│   ├── vite.config.js             # proxy /api -> backend en dev
│   └── src/
│       ├── api/client.js          # cliente HTTP
│       ├── components/  pages/  modules/
│       └── App.jsx                # pantalla inicial con estado de la API
├── docs/arquitectura.md           # módulos y plan de etapas
├── docker-compose.yml             # db + backend + frontend (desarrollo)
└── Makefile                       # atajos: make up / test / migrate …
```

## Levantar el proyecto

### Opción A — Docker (recomendada)

Requisitos: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
abierto y Git. En macOS los comandos van en la app Terminal; en Windows, en PowerShell.

1. Descargar el proyecto:

```bash
git clone https://github.com/ddelvallecabral-cloud/hm.git
```

```bash
cd hm
```

2. Crear la configuración local a partir del ejemplo (en Windows: `copy backend\.env.example backend\.env`):

```bash
cp backend/.env.example backend/.env
```

3. Abrir `backend/.env` con un editor de texto y cambiar al menos
   `DJANGO_SUPERUSER_PASSWORD` (contraseña del administrador inicial) y
   `DJANGO_SECRET_KEY`.

4. Levantar todo (la primera vez tarda unos minutos en descargar e instalar):

```bash
docker compose up -d --build
```

Al arrancar se aplican las migraciones y se crea el usuario administrador
definido en `.env`.

- **Registrar cobranza:** <http://localhost:5173> (ingresar con el usuario administrador)
- **Administración** (usuarios, roles, clientes, parámetros): <http://localhost:8000/admin/>
- **API:** <http://localhost:8000/api/health/> → `{"status": "ok", "database": "ok"}`

5. Opcional: cargar datos de demostración (3 clientes y 6 facturas marcados
   "(DEMO)", usuarios `demo_tesorero` y `demo_cobrador` con la contraseña que elijas):

```bash
docker compose exec backend python manage.py cargar_demo --clave elegir-una-clave
```

Otros comandos útiles:

```bash
docker compose logs -f backend
```

```bash
docker compose down
```

`docker compose down` detiene todo y conserva los datos; `docker compose down -v`
además **borra la base de datos**. PostgreSQL queda accesible sólo desde la
misma computadora en el puerto 5433 (configurable con `DB_PUERTO_LOCAL`).
Con `make` instalado existen atajos: `make up`, `make logs`, `make test`.

### Opción B — Local sin Docker

Requisitos: Python 3.13, Node 22, PostgreSQL 16 en marcha con una base y
usuario que coincidan con `backend/.env`.

```bash
cd backend && python -m venv .venv && . .venv/bin/activate
```

```bash
pip install -r requirements/dev.txt
```

```bash
cp .env.example .env && python manage.py migrate && python manage.py runserver
```

En otra terminal:

```bash
cd frontend && npm install && npm run dev
```

Tests del backend:

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test
```

## Entornos

Se elige con `DJANGO_SETTINGS_MODULE`:

| Entorno | Módulo                  | Características                                                                 |
|---------|-------------------------|---------------------------------------------------------------------------------|
| dev     | `config.settings.dev`   | `DEBUG=True`, lee `backend/.env`, emails a consola, auth básica + sesión en API |
| test    | `config.settings.test`  | Igual que dev, hashing de contraseñas rápido                                    |
| prod    | `config.settings.prod`  | `DEBUG=False`; **falla al iniciar** si faltan `DJANGO_SECRET_KEY` o `POSTGRES_PASSWORD`; HTTPS forzado, HSTS, cookies seguras, SMTP |

`manage.py` usa **dev** por defecto; `wsgi.py`/`asgi.py` (lo que corre Gunicorn) usan **prod**.

### Despliegue en producción (resumen)

```bash
docker build -t crm-tesoreria-backend ./backend
```

Ejecutar el contenedor con las variables de producción inyectadas por el
orquestador o el gestor de secretos (nunca un `.env` versionado), correr
`python manage.py migrate` y `python manage.py collectstatic --noinput` en cada
release, y servir detrás de un proxy HTTPS que envíe `X-Forwarded-Proto`.
Validar la configuración con `python manage.py check --deploy`.

## Variables de configuración

Todas están en [`backend/.env.example`](backend/.env.example).

| Variable | Uso | Dev | Prod |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Entorno activo | `config.settings.dev` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Firma de sesiones/tokens | valor de ejemplo | **obligatoria**, aleatoria |
| `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD`, `DJANGO_SUPERUSER_EMAIL` | Administrador inicial que crea `docker compose` al arrancar | `admin` / cambiar | no usar (crear con `createsuperuser`) |
| `DJANGO_ALLOWED_HOSTS` | Dominios servidos | `localhost,127.0.0.1` | dominio real |
| `LOG_LEVEL` | Nivel de log | `INFO` | `INFO` / `WARNING` |
| `POSTGRES_DB` / `_USER` / `_HOST` / `_PORT` | Conexión a la BD | locales | servidor de BD |
| `POSTGRES_PASSWORD` | Contraseña BD | `tesoreria` | **obligatoria** |
| `DB_CONN_MAX_AGE` | Conexiones persistentes (s) | 60 | 60 |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | Origen del frontend | `http://localhost:5173` | URL https del frontend |
| `CRM_MONEDA_BASE` | Moneda de consolidación | `PYG` | `PYG` |
| `CRM_EXIGIR_OC` | Exigir N° de OC a profesionales y pymes | `false` | `false` |
| `CRM_TOPE_MENSUAL_USD` | Tope adicional para intereses en USD (% mensual) | `1.00` | `1.00` |
| `CRM_USAR_TASA_BCP_SIN_PACTO` | Si la factura no pactó tasa, usar el tope legal como tasa moratoria | `true` | según asesoría legal |
| `CRM_PERMITIR_TASA_MES_ANTERIOR` | Si falta la tasa BCP del mes, usar la última cargada (con alerta) | `true` | `true` |
| `EMPRESA_RUC`, `EMPRESA_TIMBRADO` | Datos de la empresa | `80013339-0` | datos reales |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Avisos de cobranza por correo | no se usan (consola) | SMTP real |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | Endurecimiento HTTPS | — | `True`, `31536000` |

Frontend ([`frontend/.env.example`](frontend/.env.example)): `VITE_API_URL`
(vacío = mismo origen) y `VITE_PROXY_TARGET` (backend al que el servidor de
desarrollo de Vite redirige `/api`).


## API disponible

Todas las rutas requieren sesión iniciada (en dev también acepta autenticación
básica). Los montos se envían y devuelven como texto decimal.

| Método | Ruta | Quién | Descripción |
|---|---|---|---|
| GET | `/api/health/` | público | Estado de la API y la base |
| GET | `/api/core/me/` | todos | Usuario actual y rol |
| GET | `/api/core/auditoria/` | administrador | Bitácora (`?modelo=facturacion.Factura&objeto_id=&usuario=&accion=&campo=fecha_vencimiento&desde=&hasta=`) |
| GET, POST | `/api/clientes/` | lectura todos / alta tesorero | Filtros `?tipo=&condicion_pago=&q=` |
| GET, PATCH | `/api/clientes/<id>/` | lectura todos / edición tesorero | `motivo` opcional para la auditoría |
| GET, POST | `/api/facturacion/ordenes-compra/` | lectura todos / alta tesorero | Sólo profesionales y pymes |
| GET, POST | `/api/facturacion/facturas/` | lectura todos / alta tesorero | Búsqueda `?q=` (número, cliente o RUC); alta con `items`; totales e IVA calculados |
| GET, PATCH | `/api/facturacion/facturas/<id>/` | lectura todos / edición tesorero | Datos SIFEN de referencia, prórroga de vencimiento (con `motivo`), observaciones |
| POST | `/api/facturacion/facturas/<id>/anular/` | tesorero | Requiere `motivo` |
| GET | `/api/core/csrf/`, POST `/api/core/login/`, `/api/core/logout/` | público / todos | Sesión para el frontend |
| GET, POST | `/api/core/usuarios/` | administrador | Usuarios y roles (`?rol=&activo=`) |
| PATCH | `/api/core/usuarios/<id>/` | administrador | Cambiar rol, datos, contraseña o acceso (`motivo` para la auditoría) |
| GET | `/api/facturacion/facturas/<id>/historial/` | todos (auditoría sólo tesorería) | Pagos, gestiones y cambios de estado o vencimiento |
| POST | `/api/cobranzas/registrar-cobranza/` | tesorero | `{factura, monto, medio, fecha, referencia}`: pago de una factura; cliente y moneda salen de la factura |
| GET | `/api/cobranzas/facturas-por-cobrar/?q=` | todos | Buscador por cliente, RUC o número (`001-001-0000123` o `123`) |
| POST | `/api/cobranzas/cobro-contado/` | tesorero | `{factura, medio, referencia}` → cobra el saldo y deja la factura pagada |
| GET, POST | `/api/cobranzas/pagos/` | lectura todos / alta tesorero | Pago total o parcial de una factura: `{factura, monto, medio, fecha, moneda, referencia}` (filtros `?factura=&cliente=`) |
| GET | `/api/cobranzas/pagos/<id>/` | todos | Detalle del pago, con saldo y estado actuales de la factura |
| POST | `/api/cobranzas/pagos/<id>/anular/` | tesorero | Requiere `motivo`; restituye saldos |
| GET, POST | `/api/cobranzas/gestiones/` | todos | Llamadas, correos, WhatsApp, visitas, promesas de pago (`?cliente=&factura=&promesas_pendientes=1`) |
| GET, PATCH | `/api/cobranzas/gestiones/<id>/` | todos (el cobrador sólo las suyas) | Completar resultado, promesa o próxima acción |
| POST | `/api/cobranzas/gestiones/<id>/revisar/` | tesorero | Decisión de tesorería: `aprobada` o `modificada` con `mensaje_final` |
| POST | `/api/cobranzas/gestiones/verificar/` | todos | Alertas que tendría una gestión, sin guardarla |
| GET | `/api/cobranzas/recomendaciones/?factura=` | todos | Tono, canal y mensaje sugerido según los días de atraso |
| GET | `/api/cobranzas/alertas/` | todos | Próximas a vencer (`?dias=`) y vencidas con días de atraso |
| GET | `/api/tesoreria/dashboard/?moneda=&fecha=&dias_dso=90` | todos | Cartera agrupada por aging, interés por mora por factura, totales PYG/USD y DSO (`&formato=csv`) |
| GET | `/api/reportes/estado-cuenta/<cliente_id>/?desde=&hasta=` | todos | Estado de cuenta por moneda con saldo inicial, movimientos y pendientes con interés (`&formato=csv`) |
| GET | `/api/reportes/iva/?anio=&mes=` | todos | IVA débito fiscal del mes, en Gs. (`&formato=csv`) |
| GET | `/api/reportes/oc-pendientes/?cliente=` | todos | Facturas con OC y saldo, y OC con monto sin facturar (`&formato=csv`) |
| GET | `/api/intereses/facturas/<id>/?fecha=` | todos | Interés moratorio a hoy o a una fecha (futura = simulador) |
| GET, POST | `/api/intereses/tasas-bcp/` | lectura todos / alta administrador | Tasas máximas BCP por mes y moneda (`?moneda=&anio=`) |
| PATCH | `/api/intereses/tasas-bcp/<id>/` | administrador | Corregir una tasa cargada |
| GET | `/api/intereses/alertas/?revisada=false` | todos | Facturas con tasa ajustada al tope o calculadas con la tasa de un mes anterior |
| POST | `/api/intereses/alertas/<id>/revisada/` | tesorero | Marcar alerta como revisada |
| GET | `/api/cobranzas/cuenta-corriente/<cliente_id>/` | todos | Facturas abiertas, saldo vencido y últimos pagos por moneda |

Ejemplo de alta de factura a crédito para una pyme:

```json
{
  "cliente": 2, "orden_compra": 5,
  "timbrado": "12345678", "establecimiento": "001", "punto_expedicion": "001", "numero": "0000123",
  "fecha_emision": "2026-11-27", "condicion": "credito", "plazo_dias": 60, "moneda": "PYG",
  "precios_incluyen_iva": true,
  "items": [
    {"descripcion": "Varilla conformada 12 mm x 12 m", "unidad": "BARRA",
     "cantidad": "100", "precio_unitario": "110000"}
  ]
}
```

Respuesta (extracto): `base_imponible = 10000000.00`, `iva = 1000000.00`,
`total = 11000000.00`, `fecha_vencimiento = 2027-01-26`, `estado = pendiente`.
`orden_compra` puede omitirse.

Pago parcial de esa factura:

```json
{"factura": 15, "fecha": "2026-12-10", "monto": "4000000",
 "medio": "transferencia", "referencia": "SIPAP 889123"}
```

→ la factura queda `pagada_parcial` con `saldo = 7000000.00`.

### Roles

| Acción | Administrador | Tesorero | Cobrador |
|---|:-:|:-:|:-:|
| Consultar clientes, facturas, OC, pagos, alertas, cuenta corriente | ✔ | ✔ | ✔ |
| Registrar gestiones de cobro y promesas de pago | ✔ | ✔ | ✔ (edita sólo las suyas) |
| Revisar gestiones con alertas y decidir el mensaje final | ✔ | ✔ | |
| Crear o editar clientes, facturas y OC | ✔ | ✔ | |
| Registrar o anular pagos | ✔ | ✔ | |
| Anular facturas, cambiar vencimientos | ✔ | ✔ | |
| Ver tasas BCP y alertas de tasa | ✔ | ✔ | |
| Cargar tasas BCP | ✔ | | |
| Consultar la auditoría completa | ✔ | | |
| Ver en cada factura quién cambió su estado o vencimiento | ✔ | ✔ | |
| Crear usuarios, asignar roles, activar/desactivar | ✔ | | |

Los usuarios y roles se gestionan en la pantalla **Usuarios** (sólo
administradores). Cada cambio de rol o de acceso queda en la auditoría. Un
administrador no puede quitarse su propio rol ni desactivarse. Los
administradores también tienen acceso al panel técnico de Django (`/admin/`).

### Auditoría

Clientes, órdenes de compra, facturas, pagos, gestiones de cobro, tasas BCP y
usuarios registran en la tabla `auditoria` cada alta, cambio y baja: usuario,
IP, fecha y hora, campos con valor anterior y nuevo, y el motivo si se
informó. La bitácora no se puede editar ni borrar (tampoco desde el admin).

- **Quién cambió un estado de pago:** cada pago registrado o anulado
  actualiza el saldo y el estado de la factura, y el cambio queda con el
  usuario y el motivo ("Pago #12", "Anulación del pago #12: cheque rechazado").
- **Quién cambió un vencimiento:** la prórroga exige un motivo y queda con el
  usuario, la fecha anterior y la nueva.
- **Dónde se ve:** en la ficha de cada factura (sección Historial, para
  tesorería y administración) y en la pantalla **Auditoría** (administradores),
  filtrable por tipo de registro, campo modificado (estado, vencimiento,
  anulación de pago, rol…), usuario y fechas.

### Reglas de negocio implementadas

- **Clientes:** RUC con dígito verificador módulo 11 de la SET, obligatorio
  para profesionales y pymes. Crédito sólo a 30, 60 o 90 días y con límite
  mayor a 0. `requiere_orden_compra` se calcula a partir del tipo de cliente.
- **IVA 10% exacto (Ley 6380/2019):** la factura guarda `base_imponible`,
  `iva` y `total`, siempre calculados por el sistema (no se aceptan desde la
  API). El IVA es **exactamente el 10% de la base**, redondeado a la unidad de
  la moneda (Gs. sin decimales, USD con 2). Se valida en el modelo y además con
  una restricción `CHECK` en PostgreSQL, así que ningún proceso puede guardar
  otro valor. Con `precios_incluyen_iva = true` (lo habitual) el IVA se
  **extrae**: `base = total × 100/110`, `IVA = base × 10%`. Con `false` se suma.
  Nunca se aplica IVA sobre un precio que ya lo incluye. Por el redondeo a
  guaraníes enteros, base + IVA puede diferir del total en 1 Gs. en algunos
  importes (criterio confirmado con el proveedor de facturación electrónica).
- **Orden de compra:** opcional para profesionales y pymes (el campo se
  muestra, pero no bloquea la venta) y rechazada para particulares. Con
  `CRM_EXIGIR_OC=true` vuelve a ser obligatoria para profesionales y pymes. Debe ser del mismo cliente y la misma moneda, y lo facturado no
  puede superar su monto. Su estado (abierta / parcial / facturada) se actualiza solo.
- **Crédito:** el cliente debe tener crédito habilitado y el plazo no puede
  superar el pactado. El vencimiento se calcula como emisión + plazo. La deuda
  abierta más la nueva factura, convertida a guaraníes, no puede superar el
  límite de crédito.
- **USD:** se exige tipo de cambio, que se usa para el límite de crédito y
  luego para el reporte de IVA.
- **Retención de IVA:** `porcentaje_retencion_iva` informado por factura
  (verificar el porcentaje en la resolución vigente de la SET).
- **Datos SIFEN de referencia:** al cargar una factura se pueden registrar el
  CDC (44 dígitos, se valida el dígito verificador), timbrado, numeración y
  estado del documento. Una factura registrada como aprobada no se puede
  modificar ni anular en el CRM hasta marcarla como cancelada. El CRM no emite
  ni envía documentos a la SET.

- **Estados de factura:**

  |                   | sin pagos   | con pagos parciales                    | saldo 0 |
  |-------------------|-------------|----------------------------------------|---------|
  | antes de vencer   | `pendiente` | `pagada_parcial`                       | `pagada` |
  | después de vencer | `vencida`   | `vencida_pago_parcial` (Vencida y en proceso de pago parcial) | `pagada` |

  `anulada` se conserva para anulaciones. El paso a vencida lo hace el comando
  diario `actualizar_vencidas` y también cualquier pago posterior.
- **Saldo pendiente:** `Factura.calcular_saldo_pendiente(al=fecha)` (o
  `cobranzas.services.saldo_pendiente`) lo recalcula desde los pagos no
  anulados, opcionalmente a una fecha de corte; el campo `saldo` guarda ese
  valor y se actualiza con cada pago o anulación.

### Cobranzas

- **Contado:** `cobro-contado` crea el pago por el saldo y deja la factura
  `pagada` en una sola operación.
- **Pagos (esquema simple):** cada `Pago` pertenece a **una** factura (FK),
  con monto, fecha, medio de pago y moneda (la de la factura). Si el monto es
  menor al saldo la factura queda `pagada_parcial`; si lo cubre, `pagada`; si
  lo supera, se rechaza. Un cobro que cancela varias facturas se registra
  como un pago por factura con la misma referencia. Anular un pago (cheque
  rechazado, error) restituye el saldo. Transferencias y cheques
  exigen número de referencia. El comprobante de retención de IVA se registra
  como un pago con medio `retencion`.
- **Pantalla "Registrar cobranza"** (<http://localhost:5173>): se busca la
  factura por cliente, RUC o número, se ve total, cobrado y saldo, se carga
  monto (acepta `4.000.000`), fecha, medio y referencia, y antes de confirmar
  muestra en qué estado quedará la factura. Un monto mayor al saldo no se acepta.
  El cobrador puede consultar, pero sólo tesorería registra.
- **Gestiones de cobro (alertas, sin bloqueos):** se registra el historial de
  llamadas, correos, WhatsApp, visitas, notas y promesas de pago. El sistema
  **nunca impide** registrar una gestión: evalúa buenas prácticas y, si algo
  conviene revisarlo, guarda alertas y deja la gestión *pendiente de revisión*.
  Tesorería decide: la aprueba tal cual o escribe el mensaje final que se
  comunicará al cliente (queda auditado). Generan alerta:
  - contactos fuera de 8:00–19:00 de lunes a viernes, sábados después de las
    12:00, domingos o feriados (tabla `Feriado`);
  - más de 3 contactos con el mismo cliente en 7 días;
  - WhatsApp/SMS sin consentimiento registrado (`acepta_whatsapp`);
  - expresiones que pueden resultar intimidatorias o involucrar a terceros.

  `recomendaciones/?factura=` sugiere tono, canal y un texto con los datos
  reales de la factura según el atraso (por vencer, 1–15, 16–30, 31–60 y más
  de 60 días), más una lista de buenas prácticas. Los criterios se ajustan en
  `/admin/` → Parámetros de cobranza y deben revisarse con la asesoría legal
  (Ley 1334/98 de Defensa del Consumidor). Las promesas vencidas se marcan como
  cumplidas o incumplidas con el comando diario `evaluar_promesas`.

### Historial de gestiones de cobro por factura

En **Facturas** → elegir una factura:

- **Gestiones de cobro:** llamadas, correos, WhatsApp, visitas, notas y
  promesas de pago de esa factura, con quién las registró. Desde ahí mismo se
  registra una gestión nueva: el botón "Usar mensaje sugerido" propone un texto
  según los días de atraso y "Revisar recomendaciones" muestra las alertas de
  buenas prácticas antes de guardar.
- **Revisión de tesorería:** las gestiones con alertas quedan pendientes; el
  tesorero las aprueba tal cual o con el mensaje final que se comunicará. La
  pantalla **Gestiones** reúne todas las pendientes y las promesas por evaluar.
- **Historial:** línea de tiempo con pagos, gestiones y cambios de estado o
  vencimiento (usuario, fecha y motivo).

API: `GET /api/facturacion/facturas/<id>/historial/` y
`GET /api/cobranzas/gestiones/?factura=<id>`.

### Intereses por mora

**Base legal aplicada** (validar con la asesoría legal):

- **Código Civil, Art. 475:** los intereses moratorios no pueden superar las
  tasas máximas fijadas por el BCP; lo pactado por encima es nulo en el exceso.
- **Ley N° 489/95, Art. 44 (mod. por Ley N° 2339/03):** desde la mora, el
  interés compensatorio pactado pasa a ser moratorio y no puede superar la tasa
  originalmente pactada. No se capitalizan intereses.
- **Moneda extranjera:** además del tope BCP para USD, se aplica un tope de
  **1% mensual** (12% anual, `CRM_TOPE_MENSUAL_USD`); se usa el menor.

**Tabla `tasas_referencia_bcp`** (`TasaReferenciaBCP`): mes, año, moneda
(PYG/USD), tasa máxima anual y fuente (resolución o comunicado del BCP). No hay
tasas fijas en el código. `python manage.py cargar_tasas_ejemplo` carga los
valores de referencia de enero y agosto de 2026 (PYG 27,06% y 27,26%; USD
11,04% y 11,25%) indicados en la especificación.

#### Cómo cargar las tasas BCP cada mes

Cuando el BCP publica las tasas máximas del mes (límite de usura), un usuario
**administrador**:

1. Entra al CRM → **Tasas BCP**.
2. En "Cargar tasa del mes" elige mes y año, moneda **Guaraníes**, escribe la
   tasa máxima anual (por ejemplo `27,26`) y en **Fuente** la resolución o
   comunicado del BCP (y el enlace si lo hay). Guarda.
3. Repite con moneda **Dólares**.
4. Revisa en la tabla que el mes tenga las dos tasas (si falta una, dice "falta").
5. Revisa las **Alertas de tasa**: facturas cuya tasa pactada se ajustó al
   tope o que se calcularon con la tasa de un mes anterior. El tesorero las
   marca como revisadas.

Reglas:

- Hay una sola tasa por mes y moneda; para corregir una tasa ya cargada, el
  administrador la edita desde `/admin/` → Tasas de referencia BCP (el cambio
  queda en la auditoría).
- El interés usa la tasa del **mes de vencimiento** de cada factura. Si ese mes
  no está cargado, usa la última tasa anterior y deja una alerta; si no hay
  ninguna, no calcula y avisa que falta cargarla.
- Conviene cargarlas apenas se publican: las facturas que vencen ese mes las necesitan.

También por API (administrador):

```bash
curl -u admin:CLAVE -X POST http://localhost:8000/api/intereses/tasas-bcp/ -H "Content-Type: application/json" -d '{"anio": 2026, "mes": 12, "moneda": "PYG", "tasa_maxima_anual": "27.30", "fuente": "Resolución BCP N° ..."}'
```

**`calcular_interes_moratorio(factura, fecha_calculo)`** (`apps/intereses/services.py`):

1. Sólo actúa si la factura está vencida a la fecha de cálculo y tiene saldo.
2. Toma la tasa pactada de la factura (`tasa_interes_anual`) y la compara con
   el tope del **mes de vencimiento** (y el 1% mensual en USD). Si la supera, la
   ajusta al tope y registra una alerta (`AlertaTasa`, visible en
   `/api/intereses/alertas/` y en el admin). Si la factura no pactó tasa, usa
   el tope como tasa de referencia (configurable). Si falta la tasa BCP del mes,
   usa la última cargada y registra otra alerta; si no hay ninguna, no calcula
   y pide cargarla.
3. Interés diario = saldo de capital × tasa moratoria / 365.
4. Multiplica por los días de atraso, contados desde el día siguiente al vencimiento.
5. Nunca capitaliza: la base es sólo el capital. Si hubo pagos después del
   vencimiento, el cálculo se divide en tramos (cada pago reduce el capital
   desde su fecha) y los intereses nunca se suman a la base.
6. Devuelve capital, días de atraso, tasa pactada, topes, tasa aplicada (anual
   y diaria), interés diario, interés acumulado, total, tramos y alertas.

El redondeo se hace una sola vez al final (Gs. sin decimales, USD con 2). La
pantalla "Registrar cobranza" muestra el interés a hoy como dato informativo:
los pagos se aplican al capital. Cobrar el interés requiere emitir el
documento correspondiente (nota de débito o factura); definir su tratamiento
de IVA con el contador.

#### Casos de prueba

Los dos casos están automatizados (`apps/intereses/tests/test_interes.py`,
clase `EjemplosReadmeTest`):

```bash
docker compose exec -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test apps.intereses
```

Para reproducirlos a mano en el CRM:

1. Cargar las tasas de ejemplo:

```bash
docker compose exec backend python manage.py cargar_tasas_ejemplo
```

2. En **Clientes**, crear una pyme a crédito (60 días, límite suficiente).
3. En **Facturas → Cargar factura**, cargar la factura del caso con la fecha de
   emisión, el plazo, la moneda y la tasa pactada indicados (precios con IVA
   incluido, un ítem por el total).
4. Consultar el interés a la fecha de cálculo del caso:
   `http://localhost:8000/api/intereses/facturas/<id>/?fecha=AAAA-MM-DD`
   (con la sesión iniciada en el navegador). La respuesta debe coincidir con
   los resultados de abajo.

#### Caso de prueba 1 — Factura en guaraníes vencida hace 45 días

Factura: emisión 11/07/2026, crédito 30 días, total Gs. 15.000.000, tasa pactada 30%.
Consulta: `?fecha=2026-09-24`.

| Dato | Valor |
|---|---|
| Saldo de capital | Gs. 15.000.000 |
| Vencimiento | 10/08/2026 · fecha de cálculo 24/09/2026 |
| Tasa pactada | 30% anual |
| Tope BCP PYG 08/2026 | 27,26% anual |

1. La factura está vencida: corresponde calcular.
2. 30% > 27,26% → la tasa se **ajusta a 27,26%** y se registra la alerta.
3. Interés diario = 15.000.000 × 27,26% / 365 = **Gs. 11.202,74**
4. Días de atraso: del 11/08 al 24/09 = **45 días**.
5. Interés acumulado = 11.202,7397 × 45 = 504.123,29 → **Gs. 504.123**
6. Total a cobrar = 15.000.000 + 504.123 = **Gs. 15.504.123**

Resultado esperado: `dias_atraso` 45, `tasa_aplicada_anual` 27.26,
`tasa_ajustada` true, `interes_acumulado` 504123.00, `total` 15504123.00 y
una alerta de tasa ajustada en **Tasas BCP → Alertas**.

#### Caso de prueba 2 — Factura en dólares vencida hace 20 días

Factura: emisión 21/07/2026, crédito 30 días, total US$ 25.000, tipo de cambio cualquiera, sin tasa pactada (0).
Consulta: `?fecha=2026-09-09`.

| Dato | Valor |
|---|---|
| Saldo de capital | US$ 25.000,00 |
| Vencimiento | 20/08/2026 · fecha de cálculo 09/09/2026 |
| Tasa pactada | 0% (sin interés explícito) |
| Tope BCP USD 08/2026 | 11,25% anual |
| Tope 1% mensual | 12% anual |

1. La factura está vencida: corresponde calcular.
2. Tope aplicable = el menor entre 11,25% y 12% = **11,25%**. Sin tasa
   pactada, se usa el tope como tasa de referencia (queda indicado en las alertas).
3. Interés diario = 25.000 × 11,25% / 365 = **US$ 7,7055**
4. Días de atraso: del 21/08 al 09/09 = **20 días**.
5. Interés acumulado = 7,70548 × 20 = 154,1096 → **US$ 154,11**
6. Total a cobrar = 25.000,00 + 154,11 = **US$ 25.154,11**

Resultado esperado: `dias_atraso` 20, `tope_usd_anual` 12.00,
`tasa_aplicada_anual` 11.25, `origen_tasa` "tope_sin_tasa_pactada",
`interes_acumulado` 154.11, `total` 25154.11.

Variante: si la tasa BCP de USD de ese mes fuera 13,5%, el tope de 1% mensual
(12%) sería el más bajo y la tasa se ajustaría a 12% (test
`test_tope_1_por_ciento_mensual_usd`).

### Pantallas

En <http://localhost:5173> (el menú muestra sólo lo que cada rol puede usar):

| Pantalla | Para qué |
|---|---|
| Dashboard | Cartera por aging, interés por mora, totales PYG/USD, DSO |
| Facturas | Buscar y cargar facturas emitidas; ficha con gestiones, historial, prórroga y anulación |
| Registrar cobranza | Cargar pagos totales o parciales |
| Gestiones | Gestiones pendientes de revisión, promesas de pago, últimas gestiones |
| Clientes | Alta y edición de clientes, condiciones de crédito, contacto de cobranza |
| Reportes | Estado de cuenta, IVA por período, OC pendientes |
| Tasas BCP | Carga mensual de tasas (administrador) y alertas de tasa |
| Usuarios | Usuarios y roles (administrador) |
| Auditoría | Quién cambió qué y cuándo (administrador) |

**Identidad visual:** sigue el Manual de Marca Hierro Metal 2026: negro
`#1A1A1A`, blanco y amarillo `#FFD100` sólo como acento (filetes, indicadores
de selección; nunca como color de texto corrido), Barlow Condensed en títulos
y Barlow en textos, y el logo en su versión "placa" (sobre placa blanca) en
la barra negra, a 96 px de ancho (mínimo de marca: 90 px). El logo está en
`frontend/public/marca/`.

### Dashboard y reportes

Todos los roles pueden ver el dashboard y los reportes. Cada vista y reporte se puede
descargar en CSV (separador `;`, abre directo en Excel).

**Dashboard de cartera** (`#dashboard`):

- Facturas con saldo agrupadas por aging según los días de atraso a la fecha
  de corte: corriente (no vencidas), 1–30, 31–60, 61–90 y más de 90 días.
- Columna **Interés por mora acumulado** por factura (mismo cálculo de la
  fase 5) y total con interés. Filtro por moneda: todas, PYG o USD.
- **Total de cartera por cobrar** separado en PYG y USD (nunca se suman
  monedas), con lo vencido y el interés acumulado.
- **DSO** = cuentas por cobrar a crédito ÷ ventas a crédito de los últimos 90
  días × 90. Se muestra además el **cobro real promedio**: días entre emisión y
  pago de los cobros del período, ponderado por monto.
- Fecha de corte opcional: recalcula saldos, aging e intereses a esa fecha.

**Reportes** (`#reportes`):

- **Estado de cuenta por cliente:** por moneda, saldo inicial al comienzo del
  período, facturas (debe) y pagos (haber) con saldo acumulado, totales, y las
  facturas pendientes al cierre con su interés por mora.
- **IVA por período (débito fiscal):** facturas emitidas en el mes, no
  anuladas, con base imponible, IVA 10% y total; las de USD se convierten a
  guaraníes con el tipo de cambio de cada factura. Muestra el débito fiscal,
  las retenciones de IVA informadas y cuántas facturas aún no tienen
  aprobación SIFEN; las rechazadas o canceladas en SIFEN se listan aparte y no
  suman. Es un insumo para el Formulario 120; confirmar con el contador el
  tipo de cambio exigido por la SET.
- **Facturas con OC pendientes de conciliación:** facturas vinculadas a una
  orden de compra que todavía tienen saldo, y órdenes de compra con monto aún
  sin facturar.

### Tareas programadas

Ejecutar una vez por día (cron o el programador del servidor):

```bash
python manage.py actualizar_vencidas && python manage.py evaluar_promesas
```

## Próximos pasos

Instalación en la computadora de la empresa con Docker (sección "Levantar el
proyecto"). Ver [`docs/arquitectura.md`](docs/arquitectura.md#plan-de-etapas).
