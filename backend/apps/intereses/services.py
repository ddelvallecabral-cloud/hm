"""Cálculo del interés moratorio de una factura vencida (PYG o USD).

`calcular_interes_moratorio(factura, fecha_calculo)`:

1. Sólo actúa si la factura está vencida a la fecha de cálculo (vencimiento
   anterior a esa fecha, con saldo de capital y no anulada).
2. Tasa: se parte de la tasa pactada en la factura (`tasa_interes_anual`).
   Tope legal = tasa máxima del BCP del MES DE VENCIMIENTO para la moneda
   (Código Civil, Art. 475). En USD además rige el tope de 1% mensual
   (12% anual, configurable con CRM_TOPE_MENSUAL_USD): se usa el menor.
   Si la pactada supera el tope, se ajusta al tope y se registra una alerta
   (`AlertaTasa`). La moratoria nunca supera la pactada (Ley 489/95, Art. 44).
   Si la factura no tiene tasa pactada (0%), se usa el tope como tasa de
   referencia (CRM_USAR_TASA_BCP_SIN_PACTO=true, por defecto) o no se calcula
   interés (false). Esta regla debe validarse con la asesoría legal.
3. Interés diario = saldo de capital × tasa moratoria anual / 365.
4. Se multiplica por los días de atraso, contados desde el día siguiente al
   vencimiento hasta la fecha de cálculo inclusive.
5. Sin capitalización: la base es siempre el saldo de CAPITAL. Los pagos
   reducen el capital desde su fecha (por eso el cálculo se hace por tramos);
   los intereses nunca se suman a la base.
6. Devuelve capital, días de atraso, tasa aplicada, interés acumulado y total.

Redondeo: el resultado se redondea una sola vez (Gs. a 0 decimales, USD a 2);
nunca se redondea el interés diario intermedio.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Q, Sum
from django.utils import timezone

from apps.facturacion.models import Factura

from .models import AlertaTasa, TasaReferenciaBCP

CERO = Decimal("0")
DIAS_ANIO = 365
DECIMALES = {"PYG": 0, "USD": 2}


class ErrorTasaNoCargada(Exception):
    """No hay ninguna tasa BCP cargada para la moneda hasta el mes de vencimiento."""


def _redondear(valor: Decimal, moneda: str) -> Decimal:
    return valor.quantize(Decimal(1).scaleb(-DECIMALES[moneda]), rounding=ROUND_HALF_UP)


@dataclass
class Tope:
    tasa: Decimal
    anio: int
    mes: int
    fuente: str

    @property
    def periodo(self) -> str:
        return f"{self.mes:02d}/{self.anio}"


def tope_bcp(moneda: str, fecha: date) -> tuple[Tope, str | None]:
    """Tasa BCP del mes de `fecha`; si falta y está permitido, la última anterior (con aviso)."""
    qs = TasaReferenciaBCP.objects.filter(moneda=moneda)
    t = qs.filter(anio=fecha.year, mes=fecha.month).first()
    aviso = None
    if t is None and settings.CRM["PERMITIR_TASA_MES_ANTERIOR"]:
        t = qs.filter(Q(anio__lt=fecha.year) | Q(anio=fecha.year, mes__lt=fecha.month)).order_by("-anio", "-mes").first()
        if t is not None:
            aviso = (f"No está cargada la tasa BCP {moneda} de {fecha.month:02d}/{fecha.year}; se usó la de "
                     f"{t.mes:02d}/{t.anio}. Cargue la tasa del mes para un cálculo exacto.")
    if t is None:
        raise ErrorTasaNoCargada(
            f"No hay tasa máxima BCP cargada para {moneda} en {fecha.month:02d}/{fecha.year}. "
            "Un administrador debe cargarla en Tasas de referencia BCP.")
    return Tope(t.tasa_maxima_anual, t.anio, t.mes, t.fuente), aviso


def _tramos(factura: Factura, fecha_calculo: date):
    """[(desde, hasta, días, capital)] entre el vencimiento y la fecha de cálculo, cortando en cada pago."""
    pagos = factura.pagos.filter(anulado=False)
    venc = factura.fecha_vencimiento
    capital = factura.total - (pagos.filter(fecha__lte=venc).aggregate(s=Sum("monto"))["s"] or CERO)
    tramos, desde = [], venc
    for fecha_pago, monto in pagos.filter(fecha__gt=venc, fecha__lte=fecha_calculo).order_by("fecha", "id") \
            .values_list("fecha", "monto"):
        if fecha_pago > desde:
            tramos.append((desde, fecha_pago, (fecha_pago - desde).days, capital))
            desde = fecha_pago
        capital = max(capital - monto, CERO)
    if fecha_calculo > desde:
        tramos.append((desde, fecha_calculo, (fecha_calculo - desde).days, capital))
    return [t for t in tramos if t[3] > 0], capital


def calcular_interes_moratorio(factura: Factura, fecha_calculo: date | None = None,
                               registrar_alertas: bool = True) -> dict:
    fecha_calculo = fecha_calculo or timezone.localdate()
    moneda = factura.moneda
    base = {
        "factura_id": factura.pk, "numero": factura.numero_completo, "moneda": moneda,
        "fecha_vencimiento": factura.fecha_vencimiento, "fecha_calculo": fecha_calculo,
        "capital": factura.calcular_saldo_pendiente(fecha_calculo), "dias_atraso": 0, "aplica": False,
        "tasa_pactada_anual": factura.tasa_interes_anual, "tasa_aplicada_anual": CERO, "tasa_aplicada_diaria": CERO,
        "tope_bcp_anual": None, "tope_bcp_periodo": None, "tope_bcp_fuente": None, "tope_usd_anual": None,
        "tope_aplicable_anual": None, "tasa_ajustada": False, "origen_tasa": None,
        "interes_diario": CERO, "interes_acumulado": CERO, "tramos": [], "alertas": [],
    }
    base["total"] = base["capital"]

    # 1. Sólo facturas vencidas a la fecha de cálculo.
    if factura.estado == Factura.Estado.ANULADA:
        return {**base, "motivo": "La factura está anulada."}
    if fecha_calculo <= factura.fecha_vencimiento:
        return {**base, "motivo": "La factura no está vencida a la fecha de cálculo."}
    if base["capital"] <= 0:
        return {**base, "motivo": "La factura no tiene saldo de capital a la fecha de cálculo."}

    alertas = []
    # 2. Tasa pactada vs. tope BCP del mes de vencimiento (y 1% mensual en USD).
    tope, aviso = tope_bcp(moneda, factura.fecha_vencimiento)
    if aviso:
        alertas.append(aviso)
    tope_aplicable = tope.tasa
    tope_usd = None
    if moneda == "USD":
        tope_usd = settings.CRM["TOPE_MENSUAL_USD"] * 12
        tope_aplicable = min(tope_aplicable, tope_usd)

    pactada = factura.tasa_interes_anual
    ajustada = False
    if pactada > 0:
        tasa, origen = pactada, "pactada"
        if pactada > tope_aplicable:
            limite = "1% mensual para moneda extranjera" if tope_usd is not None and tope_usd < tope.tasa \
                else f"tasa máxima BCP {moneda} {tope.periodo}"
            alertas.append(f"La tasa pactada {pactada}% anual supera el tope legal ({limite}: {tope_aplicable}%). "
                           f"Se ajustó a {tope_aplicable}% (Código Civil, Art. 475).")
            tasa, ajustada, origen = tope_aplicable, True, "ajustada_al_tope"
    elif settings.CRM["USAR_TASA_BCP_SIN_PACTO"]:
        tasa, origen = tope_aplicable, "tope_sin_tasa_pactada"
        alertas.append(f"La factura no tiene tasa pactada; se usa el tope legal ({tope_aplicable}% anual) como "
                       "tasa moratoria de referencia.")
    else:
        return {**base, "motivo": "La factura no tiene tasa de interés pactada.", "alertas": alertas}

    if registrar_alertas and factura.pk:
        if ajustada:
            AlertaTasa.objects.get_or_create(
                factura=factura, tipo=AlertaTasa.Tipo.AJUSTE_TOPE, periodo_tope=tope.periodo,
                defaults={"moneda": moneda, "tasa_pactada_anual": pactada, "tope_aplicado_anual": tope_aplicable,
                          "mensaje": alertas[-1][:300]})
        if aviso:
            AlertaTasa.objects.get_or_create(
                factura=factura, tipo=AlertaTasa.Tipo.TASA_MES_ANTERIOR, periodo_tope=tope.periodo,
                defaults={"moneda": moneda, "tasa_pactada_anual": pactada, "tope_aplicado_anual": tope_aplicable,
                          "mensaje": aviso[:300]})

    # 3-5. Interés simple por tramos de capital (sin capitalizar).
    tramos, capital = _tramos(factura, fecha_calculo)
    interes = sum((c * tasa / 100 / DIAS_ANIO * d for _, _, d, c in tramos), CERO)
    interes = _redondear(interes, moneda)
    dias = (fecha_calculo - factura.fecha_vencimiento).days

    return {
        **base,
        "aplica": True,
        "capital": capital,
        "dias_atraso": dias,
        "tasa_aplicada_anual": tasa,
        "tasa_aplicada_diaria": (tasa / DIAS_ANIO).quantize(Decimal("0.000001")),
        "tope_bcp_anual": tope.tasa, "tope_bcp_periodo": tope.periodo, "tope_bcp_fuente": tope.fuente,
        "tope_usd_anual": tope_usd, "tope_aplicable_anual": tope_aplicable,
        "tasa_ajustada": ajustada, "origen_tasa": origen,
        "interes_diario": (capital * tasa / 100 / DIAS_ANIO).quantize(Decimal("0.01")),
        "interes_acumulado": interes,
        "total": capital + interes,
        "tramos": [{"desde": d0 + timedelta(days=1), "hasta": d1, "dias": d, "capital": c,
                    "interes": _redondear(c * tasa / 100 / DIAS_ANIO * d, moneda)} for d0, d1, d, c in tramos],
        "alertas": alertas,
    }
