#!/usr/bin/env bash
# Instalador del CRM de Tesorería Hierro Metal (macOS / Linux).
# Uso, desde la carpeta del proyecto:   ./instalar.sh
# Es seguro volver a ejecutarlo: no borra datos ni reemplaza una configuración existente.
set -euo pipefail
cd "$(dirname "$0")"

amarillo() { printf '\033[1;33m%s\033[0m\n' "$*"; }
ok() { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
error() { printf '\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }
aleatorio() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1"; }

amarillo "== CRM de Tesorería · Hierro Metal S.R.L. =="

# 1. Docker
command -v docker >/dev/null 2>&1 || error "No se encontró Docker. Instale Docker Desktop: https://www.docker.com/products/docker-desktop/"
docker info >/dev/null 2>&1 || error "Docker no está en marcha. Abra Docker Desktop, espere a que diga 'Running' y vuelva a ejecutar ./instalar.sh"
docker compose version >/dev/null 2>&1 || error "Falta 'docker compose'. Actualice Docker Desktop."
ok "Docker en marcha"

# 2. Configuración (backend/.env)
if [ -f backend/.env ]; then
  ok "Configuración existente en backend/.env (no se modifica)"
else
  amarillo "Configuración inicial"
  read -r -p "Usuario administrador [admin]: " ADMIN_USER
  ADMIN_USER=${ADMIN_USER:-admin}
  while true; do
    read -r -s -p "Contraseña del administrador (mínimo 10 caracteres): " ADMIN_PASS; echo
    [ ${#ADMIN_PASS} -ge 10 ] || { echo "  Es muy corta."; continue; }
    case "$ADMIN_PASS" in *[\$\'\"\`\ \#\\]*) echo "  Evite \$, comillas, espacios, # y \\ en la contraseña."; continue;; esac
    read -r -s -p "Repetirla: " ADMIN_PASS2; echo
    [ "$ADMIN_PASS" = "$ADMIN_PASS2" ] && break || echo "  No coinciden."
  done
  cat > backend/.env <<ENV
# Generado por instalar.sh el $(date '+%d/%m/%Y %H:%M'). No compartir: contiene contraseñas.
DJANGO_SETTINGS_MODULE=config.settings.dev
DJANGO_SECRET_KEY=$(aleatorio 64)
DJANGO_ALLOWED_HOSTS=*
LOG_LEVEL=INFO

DJANGO_SUPERUSER_USERNAME=${ADMIN_USER}
DJANGO_SUPERUSER_PASSWORD=${ADMIN_PASS}
DJANGO_SUPERUSER_EMAIL=

POSTGRES_DB=tesoreria
POSTGRES_USER=tesoreria
POSTGRES_PASSWORD=$(aleatorio 32)
POSTGRES_HOST=db
POSTGRES_PORT=5432

CORS_ALLOWED_ORIGINS=http://localhost:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173

CRM_MONEDA_BASE=PYG
CRM_EXIGIR_OC=false
CRM_TOPE_MENSUAL_USD=1.00
CRM_USAR_TASA_BCP_SIN_PACTO=true
CRM_PERMITIR_TASA_MES_ANTERIOR=true
EMPRESA_RUC=80013339-0
EMPRESA_TIMBRADO=
ENV
  chmod 600 backend/.env
  ok "Configuración creada en backend/.env"
fi

# 3. Levantar
amarillo "Construyendo y levantando el CRM (la primera vez tarda unos minutos)…"
docker compose up -d --build

# 4. Esperar a que responda
printf "Esperando al servidor"
for i in $(seq 1 90); do
  if curl -fsS http://localhost:8000/api/health/ >/dev/null 2>&1; then echo; ok "Backend en marcha"; break; fi
  printf "."; sleep 2
  [ "$i" = 90 ] && { echo; error "El backend no respondió. Revise: docker compose logs backend"; }
done
for i in $(seq 1 90); do
  curl -fsS -o /dev/null http://localhost:5173/ 2>/dev/null && { ok "Pantallas en marcha"; break; }
  sleep 2
  [ "$i" = 90 ] && echo "Las pantallas todavía están instalándose; revise en un minuto: docker compose logs frontend"
done

# 5. Tasas BCP de referencia (enero y agosto 2026)
docker compose exec -T backend python manage.py cargar_tasas_ejemplo >/dev/null && ok "Tasas BCP de referencia cargadas (verificar con el BCP)"

IP=$( (ipconfig getifaddr en0 || ipconfig getifaddr en1 || hostname -I | awk '{print $1}') 2>/dev/null | head -1 || true)
echo
amarillo "Listo. Abra en el navegador:"
echo "  CRM (esta computadora):        http://localhost:5173"
[ -n "${IP:-}" ] && echo "  CRM (otras PCs de la oficina):  http://${IP}:5173"
echo "  Panel técnico:                 http://localhost:8000/admin/"
echo
echo "Detener:  docker compose stop      ·  Volver a iniciar:  docker compose start"
echo "El CRM se inicia solo cada vez que se abre Docker Desktop."
