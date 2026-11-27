"""Exportación CSV de reportes (separador ';' y UTF-8 con BOM para que Excel en español lo abra bien)."""
import csv
from decimal import Decimal

from django.http import HttpResponse


def _celda(v):
    if isinstance(v, Decimal):
        return f"{v:.2f}".replace(".", ",")
    return "" if v is None else v


def respuesta_csv(nombre: str, columnas: list[tuple[str, str]], filas: list[dict]) -> HttpResponse:
    """columnas = [(clave, título), ...]"""
    r = HttpResponse(content_type="text/csv; charset=utf-8")
    r["Content-Disposition"] = f'attachment; filename="{nombre}.csv"'
    r.write("﻿")
    w = csv.writer(r, delimiter=";")
    w.writerow([t for _, t in columnas])
    for f in filas:
        w.writerow([_celda(f.get(k)) for k, _ in columnas])
    return r
