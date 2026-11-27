"""Configuración común a todos los entornos."""
from pathlib import Path

from config.env import cargar_dotenv, env, env_bool, env_int, env_list

BASE_DIR = Path(__file__).resolve().parent.parent.parent
cargar_dotenv(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", "solo-para-desarrollo-cambiar")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    # Módulos del CRM de Tesorería
    "apps.core",
    "apps.clientes",
    "apps.facturacion",
    "apps.cobranzas",
    "apps.intereses",
    "apps.tesoreria",
    "apps.reportes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.audit.AuditoriaMiddleware",  # usuario/IP para la bitácora
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

# PostgreSQL en todos los entornos (los cálculos monetarios usan NUMERIC exacto).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "tesoreria"),
        "USER": env("POSTGRES_USER", "tesoreria"),
        "PASSWORD": env("POSTGRES_PASSWORD", "tesoreria"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
    }
}

AUTH_USER_MODEL = "core.Usuario"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Paraguay
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Asuncion"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))  # adjuntos de OC, KuDE, etc.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "COERCE_DECIMAL_TO_STRING": True,  # montos como string: sin pérdida de precisión
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")

# ---------------------------------------------------------------------------
# Parámetros del dominio (sólo se declaran; se usarán en etapas siguientes)
# ---------------------------------------------------------------------------
CRM = {
    "MONEDAS": ["PYG", "USD"],
    "MONEDA_BASE": env("CRM_MONEDA_BASE", "PYG"),
    # Orden de compra: opcional para profesionales/pymes salvo que se active aquí.
    "EXIGIR_OC": env_bool("CRM_EXIGIR_OC", False),
    # SIFEN - Facturación electrónica (SET). Integración real pendiente.
    "SIFEN_AMBIENTE": env("SIFEN_AMBIENTE", "test"),  # test | prod
    "SIFEN_URL_WS": env("SIFEN_URL_WS", ""),
    "SIFEN_CERT_PATH": env("SIFEN_CERT_PATH", ""),
    "SIFEN_CERT_PASSWORD": env("SIFEN_CERT_PASSWORD", ""),
    "SIFEN_ID_CSC": env("SIFEN_ID_CSC", ""),
    "SIFEN_CSC": env("SIFEN_CSC", ""),
    "EMPRESA_RUC": env("EMPRESA_RUC", ""),
    "EMPRESA_TIMBRADO": env("EMPRESA_TIMBRADO", ""),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
