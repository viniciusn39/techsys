"""Metas calibradas pelo histórico real.

Regra da casa: a meta de um indicador do ERP não é puxada do WinThor nem
digitada no chute. Olhamos os últimos 12 meses fechados já calculados do
espelho, tiramos a MEDIANA (robusta a mês atípico) e gravamos, para cada mês
do ano, meta = mediana melhorada em 5 % na direção da polaridade (maior é
melhor: +5 %; menor é melhor: −5 %). Roda todo dia 1º para os meses ainda sem
meta e ao plugar um KPI novo; o gestor pode sobrescrever à mão quando quiser.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

MESES_PADRAO = 12
MELHORIA_PADRAO = Decimal("5")


@dataclass
class Resultado:
    code: str
    base: Decimal | None
    meses_usados: int
    meta: Decimal | None
    gravadas: int
    obs: str = ""


def base_historica(indicator, meses=MESES_PADRAO, hoje=None):
    """Mediana dos últimos `meses` meses fechados (ou o valor de hoje para fotografia sem histórico)."""
    from .models import IndicatorValue

    hoje = hoje or date.today()
    mes_corrente = hoje.replace(day=1)
    historico = list(
        IndicatorValue.objects.filter(indicator=indicator, period__lt=mes_corrente)
        .order_by("-period").values_list("value", flat=True)[:meses]
    )
    historico = [Decimal(v) for v in historico if v is not None]
    if len(historico) >= 2:
        return Decimal(str(median(historico))), len(historico), ""
    atual = IndicatorValue.objects.filter(indicator=indicator, period=mes_corrente).values_list("value", flat=True).first()
    if atual is None:
        return None, len(historico), "sem histórico"
    return Decimal(atual), len(historico), "base = valor de hoje (sem meses fechados)"


def meta_a_partir_da_base(indicator, base, melhoria=MELHORIA_PADRAO):
    from .models import Indicator

    if indicator.polarity == Indicator.Polarity.MAIOR_MELHOR:
        if base <= 0:
            return None
        meta = base * (1 + Decimal(melhoria) / 100)
    else:
        meta = max(Decimal("0"), base * (1 - Decimal(melhoria) / 100))
    q = Decimal(1).scaleb(-int(indicator.decimals))
    return meta.quantize(q, rounding=ROUND_HALF_UP)


def calibrar_indicador(indicator, ano=None, meses=MESES_PADRAO, melhoria=MELHORIA_PADRAO, sobrescrever=False, hoje=None):
    """Grava a meta calibrada nos meses do ano (todos com --sobrescrever; só os sem meta caso contrário).

    Também desliga a meta do ERP (`erp_target`) do indicador: a partir daqui a
    meta é nossa e pode ser editada pelo gestor.
    """
    from .models import IndicatorTarget
    from .services import recompute_indicator

    hoje = hoje or date.today()
    ano = ano or hoje.year
    base, n, obs = base_historica(indicator, meses, hoje)
    if base is None:
        return Resultado(indicator.code, None, n, None, 0, obs)
    meta = meta_a_partir_da_base(indicator, base, melhoria)
    if meta is None:
        return Resultado(indicator.code, base, n, None, 0, "base zero em 'maior é melhor'")

    gravadas = 0
    existentes = {t.period: t for t in IndicatorTarget.objects.filter(indicator=indicator, period__year=ano)}
    for m in range(1, 13):
        periodo = date(ano, m, 1)
        t = existentes.get(periodo)
        if t and not sobrescrever:
            continue
        if t:
            if t.target_value != meta:
                t.target_value = meta
                t.save(update_fields=["target_value"])
                gravadas += 1
        else:
            IndicatorTarget.objects.create(indicator=indicator, period=periodo, target_value=meta)
            gravadas += 1
    if indicator.erp_target:
        indicator.erp_target = ""
        indicator.save(update_fields=["erp_target"])
    if gravadas:
        recompute_indicator(indicator)
    return Resultado(indicator.code, base, n, meta, gravadas, obs)


def calibrar_tenant(tenant, ano=None, meses=MESES_PADRAO, melhoria=MELHORIA_PADRAO, sobrescrever=False, apenas=None):
    """Calibra todos os indicadores ativos ligados ao ERP da empresa."""
    from .models import Indicator

    qs = Indicator.objects.filter(tenant=tenant, is_active=True).exclude(erp_metric="")
    if apenas:
        qs = qs.filter(code__in=apenas)
    return [calibrar_indicador(ind, ano, meses, melhoria, sobrescrever) for ind in qs.order_by("code")]
