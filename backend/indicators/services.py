"""Regras de cálculo de atingimento, farol e acumulado (YTD)."""
from decimal import Decimal, InvalidOperation


def compute_achievement(indicator, value, target):
    """Retorna (achievement_pct, status) respeitando a polaridade.

    maior_melhor: atingimento = real / meta.
    menor_melhor: atingimento = meta / real (gastar/perder menos que a meta => >100%).
    Farol: >=100% verde, >= yellow_threshold amarelo, senão vermelho.
    """
    from .models import Indicator, IndicatorValue

    if target is None:
        return None, IndicatorValue.Status.SEM_META

    value = Decimal(value)
    target = Decimal(target)

    try:
        if indicator.polarity == Indicator.Polarity.MENOR_MELHOR:
            if value == 0:
                # Nada gasto/perdido/vencido: meta cumprida. 100% (não "infinito"):
                # mostrar 1.000% na tela só confunde e estica o gráfico.
                pct = Decimal("100") if target >= 0 else Decimal("0")
            else:
                pct = target / value * 100
        else:
            if target == 0:
                pct = Decimal("999.99") if value >= 0 else Decimal("0")
            else:
                pct = value / target * 100
    except (ZeroDivisionError, InvalidOperation):
        return None, IndicatorValue.Status.SEM_META

    pct = max(Decimal("-999.99"), min(Decimal("999.99"), pct)).quantize(Decimal("0.01"))

    if pct >= 100:
        status = IndicatorValue.Status.VERDE
    elif pct >= indicator.yellow_threshold_pct:
        status = IndicatorValue.Status.AMARELO
    else:
        status = IndicatorValue.Status.VERMELHO
    return pct, status


def compute_ytd(indicator, year, until_period=None):
    """Acumulado do ano (real e meta) conforme a agregação do indicador."""
    from .models import Indicator

    values_qs = indicator.values.filter(period__year=year)
    targets_qs = indicator.targets.filter(period__year=year)
    if until_period is not None:
        values_qs = values_qs.filter(period__lte=until_period)
        targets_qs = targets_qs.filter(period__lte=until_period)

    values = [v.value for v in values_qs.order_by("period")]
    targets = [t.target_value for t in targets_qs.order_by("period")]

    def agg(items):
        if not items:
            return None
        if indicator.aggregation == Indicator.Aggregation.SOMA:
            return sum(items)
        if indicator.aggregation == Indicator.Aggregation.MEDIA:
            return sum(items) / len(items)
        return items[-1]

    ytd_value = agg(values)
    ytd_target = agg(targets)
    pct = None
    if ytd_value is not None and ytd_target is not None:
        pct, _ = compute_achievement(indicator, ytd_value, ytd_target)
    return {"value": ytd_value, "target": ytd_target, "achievement_pct": pct}


def recompute_indicator(indicator):
    """Recomputa farol/atingimento de todos os valores (após mudar meta/threshold)."""
    for value in indicator.values.all():
        value.save()
