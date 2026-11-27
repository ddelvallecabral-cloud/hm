# CRM de Tesorería — Hierros y productos siderúrgicos (Paraguay)

CRM para el departamento de Tesorería: seguimiento de cobranzas al contado y a
crédito, facturas en **PYG** y **USD** con **IVA 10%**, clientes
**particulares / profesionales / pymes**, datos compatibles con **SIFEN** e
**intereses por mora** según los topes del **BCP**.

> **Estado: fase 4** — clientes, roles, auditoría, facturación (IVA 10% exacto),
> cobranzas (contado, pagos parciales, gestiones con alertas) y la pantalla
> **Registrar cobranza**. Intereses por mora, tesorería y reportes vienen en las
> fases siguientes; ver [`docs/arquitectura.md`](docs/arquitectura.md).

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
│   │   │   ├── base.py            # común: apps, BD, zona horaria, DRF, parámetros CRM/SIFEN
│   │   │   ├── dev.py             # DEBUG, email a consola, auth básica para probar la API
│   │   │   ├── prod.py            # secretos obligatorios, HTTPS, HSTS, cookies seguras
│   │   │   └── test.py            # tests
│   │   ├── urls.py                # /admin, /api/health, /api/<modulo>/
│   │   ├── wsgi.py / asgi.py      # usan config.settings.prod por defecto
│   └── apps/
│       ├── core/                  # usuarios, roles, auditoría, utilidades monetarias
│       ├── clientes/              # ficha de cliente, RUC, tipo, crédito
│       ├── facturacion/           # facturas, IVA 10%, SIFEN, órdenes de compra
│       ├── cobranzas/             # pagos, aplicaciones, gestiones de cobro
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
| `EMPRESA_RUC`, `EMPRESA_TIMBRADO` | Datos del emisor | — | datos reales |
| `SIFEN_AMBIENTE` | `test` / `prod` de la SET | `test` | `prod` |
| `SIFEN_URL_WS`, `SIFEN_CERT_PATH`, `SIFEN_CERT_PASSWORD`, `SIFEN_ID_CSC`, `SIFEN_CSC` | Integración de facturación electrónica | vacías | ver nota |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Avisos de cobranza por correo | no se usan (consola) | SMTP real |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | Endurecimiento HTTPS | — | `True`, `31536000` |

Frontend ([`frontend/.env.example`](frontend/.env.example)): `VITE_API_URL`
(vacío = mismo origen) y `VITE_PROXY_TARGET` (backend al que el servidor de
desarrollo de Vite redirige `/api`).

> **Configuración adicional requerida (SIFEN):** para emitir documentos
> electrónicos hace falta estar habilitado como facturador electrónico ante la
> SET, contar con timbrado electrónico, un certificado digital de persona
> jurídica emitido por un prestador habilitado y el CSC (código de seguridad)
> que entrega la SET. Esas credenciales van sólo en variables de entorno o en
> un gestor de secretos; los archivos `.p12/.pfx/.pem` están excluidos de git.

## API disponible

Todas las rutas requieren sesión iniciada (en dev también acepta autenticación
básica). Los montos se envían y devuelven como texto decimal.

| Método | Ruta | Quién | Descripción |
|---|---|---|---|
| GET | `/api/health/` | público | Estado de la API y la base |
| GET | `/api/core/me/` | todos | Usuario actual y rol |
| GET | `/api/core/auditoria/` | administrador | Bitácora (`?modelo=facturacion.Factura&objeto_id=…&usuario=&accion=`) |
| GET, POST | `/api/clientes/` | lectura todos / alta tesorero | Filtros `?tipo=&condicion_pago=&q=` |
| GET, PATCH | `/api/clientes/<id>/` | lectura todos / edición tesorero | `motivo` opcional para la auditoría |
| GET, POST | `/api/facturacion/ordenes-compra/` | lectura todos / alta tesorero | Sólo profesionales y pymes |
| GET, POST | `/api/facturacion/facturas/` | lectura todos / alta tesorero | Alta con `items`; totales e IVA calculados |
| GET, PATCH | `/api/facturacion/facturas/<id>/` | lectura todos / edición tesorero | Datos SIFEN, prórroga de vencimiento (con `motivo`), observaciones |
| POST | `/api/facturacion/facturas/<id>/anular/` | tesorero | Requiere `motivo` |
| GET | `/api/core/csrf/`, POST `/api/core/login/`, `/api/core/logout/` | público / todos | Sesión para el frontend |
| POST | `/api/cobranzas/registrar-cobranza/` | tesorero | `{factura, monto, medio, fecha, referencia}`: pago de una factura; cliente y moneda salen de la factura |
| GET | `/api/cobranzas/facturas-por-cobrar/?q=` | todos | Buscador por cliente, RUC o número (`001-001-0000123` o `123`) |
| POST | `/api/cobranzas/cobro-contado/` | tesorero | `{factura, medio, referencia}` → cobra el saldo y deja la factura pagada |
| GET, POST | `/api/cobranzas/pagos/` | lectura todos / alta tesorero | Pago total o parcial: `imputaciones` manuales, `aplicar_automatico` o sin imputar (saldo a favor) |
| GET | `/api/cobranzas/pagos/<id>/` | todos | Detalle con aplicaciones y monto sin aplicar |
| POST | `/api/cobranzas/pagos/<id>/aplicar/` | tesorero | Aplica saldo a favor a facturas |
| POST | `/api/cobranzas/pagos/<id>/anular/` | tesorero | Requiere `motivo`; restituye saldos |
| GET, POST | `/api/cobranzas/gestiones/` | todos | Llamadas, correos, WhatsApp, visitas, promesas de pago (`?cliente=&factura=&promesas_pendientes=1`) |
| GET, PATCH | `/api/cobranzas/gestiones/<id>/` | todos (el cobrador sólo las suyas) | Completar resultado, promesa o próxima acción |
| POST | `/api/cobranzas/gestiones/<id>/revisar/` | tesorero | Decisión de tesorería: `aprobada` o `modificada` con `mensaje_final` |
| POST | `/api/cobranzas/gestiones/verificar/` | todos | Alertas que tendría una gestión, sin guardarla |
| GET | `/api/cobranzas/recomendaciones/?factura=` | todos | Tono, canal y mensaje sugerido según los días de atraso |
| GET | `/api/cobranzas/alertas/` | todos | Próximas a vencer (`?dias=`) y vencidas con días de atraso |
| GET | `/api/cobranzas/cuenta-corriente/<cliente_id>/` | todos | Facturas abiertas, saldo vencido, últimos pagos y saldo a favor por moneda |

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
{"cliente": 2, "fecha": "2026-12-10", "moneda": "PYG", "monto": "4000000",
 "medio": "transferencia", "referencia": "SIPAP 889123",
 "imputaciones": [{"factura": 15, "monto": "4000000"}]}
```

→ la factura queda `pagada_parcial` con `saldo = 7000000.00`.

### Roles

| Acción | Administrador | Tesorero | Cobrador |
|---|:-:|:-:|:-:|
| Consultar clientes, facturas, OC, pagos, alertas, cuenta corriente | ✔ | ✔ | ✔ |
| Registrar gestiones de cobro y promesas de pago | ✔ | ✔ | ✔ (edita sólo las suyas) |
| Revisar gestiones con alertas y decidir el mensaje final | ✔ | ✔ | |
| Crear o editar clientes, facturas y OC | ✔ | ✔ | |
| Registrar, aplicar o anular pagos | ✔ | ✔ | |
| Anular facturas, cambiar vencimientos | ✔ | ✔ | |
| Consultar la auditoría | ✔ | | |
| Gestionar usuarios (admin de Django) | ✔ | | |

El rol se asigna en `/admin/` → Usuarios. Un usuario con rol administrador
obtiene acceso al admin de Django automáticamente.

### Auditoría

Clientes, órdenes de compra, facturas, pagos y gestiones de cobro registran en la tabla `auditoria` cada
alta, cambio y baja: usuario, IP, fecha y hora, campos con valor anterior y
nuevo, y el motivo si se informó. En facturas se auditan estado, vencimiento,
plazo, importes, OC, datos SIFEN y anulación. La bitácora no se puede editar
ni borrar (tampoco desde el admin).

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
- **SIFEN:** se registran CDC (44 dígitos con dígito verificador), timbrado,
  establecimiento, punto de expedición, estado del documento, respuesta de la
  SET y KuDE. Un documento aprobado no se puede modificar ni anular desde el
  CRM: primero hay que registrar la cancelación ante la SET. La emisión y el
  envío del XML **no** están implementados (ver nota SIFEN más arriba).

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
- **Pagos parciales:** un pago puede repartirse entre varias facturas del mismo
  cliente y la misma moneda, sin superar el saldo de ninguna. Lo no aplicado
  queda como saldo a favor para usarlo después. `aplicar_automatico` imputa
  de la factura que vence primero a la que vence última. Anular un pago
  (cheque rechazado, error) restituye los saldos. Transferencias y cheques
  exigen número de referencia. El comprobante de retención de IVA se registra
  como un pago con medio `retencion`.
- **Pantalla "Registrar cobranza"** (<http://localhost:5173>): se busca la
  factura por cliente, RUC o número, se ve total, cobrado y saldo, se carga
  monto (acepta `4.000.000`), fecha, medio y referencia, y antes de confirmar
  muestra en qué estado quedará la factura. Un monto mayor al saldo no se acepta.
  El cobrador puede consultar, pero sólo tesorería registra.
- **Pago de una factura vs. pago de varias:** `registrar-cobranza` aplica un
  pago a una factura (el caso del día a día). El modelo `Pago` se vincula a las
  facturas mediante `AplicacionPago`, de modo que una misma transferencia
  también puede cancelar varias facturas (`/api/cobranzas/pagos/`).
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

### Tareas programadas

Ejecutar una vez por día (cron o el programador del servidor):

```bash
python manage.py actualizar_vencidas && python manage.py evaluar_promesas
```

## Próximas etapas

Ver [`docs/arquitectura.md`](docs/arquitectura.md#plan-de-etapas).
