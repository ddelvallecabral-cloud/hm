# Atajos de desarrollo (ejecutar desde la raíz del repo)
.PHONY: up down logs migrate test shell superuser

up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f backend
migrate:   ; docker compose exec backend python manage.py migrate
test:      ; docker compose exec -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test
shell:     ; docker compose exec backend python manage.py shell
superuser: ; docker compose exec backend python manage.py createsuperuser
