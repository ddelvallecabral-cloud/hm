"""Lectura tipada de variables de entorno (sin dependencias externas).

Carga opcionalmente un archivo `.env` en backend/ (sólo para desarrollo);
las variables ya definidas en el entorno tienen prioridad.
"""
import os
from pathlib import Path


def cargar_dotenv(ruta: Path) -> None:
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def env(nombre: str, default=None, requerido: bool = False) -> str:
    valor = os.environ.get(nombre, default)
    if requerido and (valor is None or valor == ""):
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {nombre}")
    return valor


def env_bool(nombre: str, default: bool = False) -> bool:
    return str(os.environ.get(nombre, default)).lower() in ("1", "true", "yes", "si", "sí")


def env_list(nombre: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(nombre, default).split(",") if x.strip()]


def env_int(nombre: str, default: int) -> int:
    return int(os.environ.get(nombre, default))
