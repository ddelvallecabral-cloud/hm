#!/bin/sh
# Arranque del backend en desarrollo (docker compose).
set -e
python manage.py migrate --noinput
# Crea el administrador inicial si se definieron DJANGO_SUPERUSER_USERNAME y DJANGO_SUPERUSER_PASSWORD en .env
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py shell -c "
from django.contrib.auth import get_user_model
U = get_user_model(); import os
n = os.environ['DJANGO_SUPERUSER_USERNAME']
if not U.objects.filter(username=n).exists():
    U.objects.create_superuser(n, os.environ.get('DJANGO_SUPERUSER_EMAIL', ''), os.environ['DJANGO_SUPERUSER_PASSWORD'], rol='administrador')
    print('Administrador creado:', n)
"
fi
exec python manage.py runserver 0.0.0.0:8000
