# CRM de Tesorería — Hierros y productos siderúrgicos (Paraguay)

CRM para el departamento de Tesorería: seguimiento de cobranzas al contado y a
crédito, facturas en **PYG** y **USD** con **IVA 10%**, clientes
**particulares / profesionales / pymes**, datos compatibles con **SIFEN** e
**intereses por mora** según los topes del **BCP**.

> **Estado: esqueleto (etapa 1).** El repositorio contiene la estructura, la
> configuración por entorno y la infraestructura para levantarlo. La lógica de
> negocio (IVA, cobranzas, intereses, reportes) se implementa en las etapas
> siguientes; ver [`docs/arquitectura.md`](docs/arquitectura.md).

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

Requisitos: Docker y Docker Compose.

```bash
cp backend/.env.example backend/.env
```

```bash
make up
```

```bash
make superuser
```

- API: <http://localhost:8000/api/health/> → `{"status": "ok", "database": "ok"}`
- Admin Django: <http://localhost:8000/admin/>
- Frontend: <http://localhost:5173>

Las migraciones se aplican solas al iniciar el backend. Tests: `make test`.

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
| `DJANGO_ALLOWED_HOSTS` | Dominios servidos | `localhost,127.0.0.1` | dominio real |
| `LOG_LEVEL` | Nivel de log | `INFO` | `INFO` / `WARNING` |
| `POSTGRES_DB` / `_USER` / `_HOST` / `_PORT` | Conexión a la BD | locales | servidor de BD |
| `POSTGRES_PASSWORD` | Contraseña BD | `tesoreria` | **obligatoria** |
| `DB_CONN_MAX_AGE` | Conexiones persistentes (s) | 60 | 60 |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | Origen del frontend | `http://localhost:5173` | URL https del frontend |
| `CRM_MONEDA_BASE` | Moneda de consolidación | `PYG` | `PYG` |
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

## Próximas etapas

Ver [`docs/arquitectura.md`](docs/arquitectura.md#plan-de-etapas).
