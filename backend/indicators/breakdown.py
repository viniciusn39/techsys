"""Quebra de um indicador por período: dia, semana, mês, semestre, ano.

Os lançamentos e as metas são mensais. Para as outras visões:

- Indicador ligado ao ERP: o valor é recalculado direto do espelho para o
  intervalo do bucket (a métrica aceita qualquer ini/fim), então dia e semana
  são exatos. Manual: dia/semana não existem (só há valor mensal); semestre e
  ano agregam os meses pela regra do indicador (soma, média ou último).
- Meta: mês é a meta cadastrada. Semestre/ano agregam as metas mensais pela
  mesma regra. Dia/semana derivam da meta do mês: se o indicador é "soma", a
  meta é proporcional aos dias (meta do mês ÷ dias do mês × dias do bucket);
  se é média ou último (um %, um prazo, um saldo), a meta do mês vale para
  qualquer dia dele.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from .models import Indicator, IndicatorTarget, IndicatorValue
from .services import compute_achievement

GRANULARIDADES = ("dia", "semana", "mes", "semestre", "ano")
PADRAO_N = {"dia": 31, "semana": 13, "mes": 12, "semestre": 4, "ano": 5}
MAX_N = {"dia": 92, "semana": 53, "mes": 36, "semestre": 10, "ano": 10}
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _mes_ini(d):
    return d.replace(day=1)


def _mes_fim(d):
    return d.replace(day=monthrange(d.year, d.month)[1])


def _mes_anterior(d):
    return (_mes_ini(d) - timedelta(days=1)).replace(day=1)


def buckets(gran, ate, n):
    """Lista de (label, ini, fim) do mais antigo ao mais recente, terminando no bucket que contém `ate`."""
    out = []
    if gran == "dia":
        for i in range(n - 1, -1, -1):
            d = ate - timedelta(days=i)
            out.append((d.strftime("%d/%m"), d, d))
    elif gran == "semana":
        seg = ate - timedelta(days=ate.weekday())
        for i in range(n - 1, -1, -1):
            ini = seg - timedelta(weeks=i)
            fim = ini + timedelta(days=6)
            out.append((f"sem {ini.isocalendar()[1]} · {ini.strftime('%d/%m')}", ini, fim))
    elif gran == "mes":
        cur = _mes_ini(ate)
        meses = []
        for _ in range(n):
            meses.append(cur)
            cur = _mes_anterior(cur)
        for m in reversed(meses):
            out.append((f"{MESES_PT[m.month - 1]}/{str(m.year)[2:]}", m, _mes_fim(m)))
    elif gran == "semestre":
        ano, sem = ate.year, 1 if ate.month <= 6 else 2
        itens = []
        for _ in range(n):
            itens.append((ano, sem))
            if sem == 1:
                ano, sem = ano - 1, 2
            else:
                sem = 1
        for ano, sem in reversed(itens):
            ini = date(ano, 1 if sem == 1 else 7, 1)
            fim = date(ano, 6, 30) if sem == 1 else date(ano, 12, 31)
            out.append((f"{sem}º sem/{ano}", ini, fim))
    elif gran == "ano":
        for ano in range(ate.year - n + 1, ate.year + 1):
            out.append((str(ano), date(ano, 1, 1), date(ano, 12, 31)))
    return out


def _agrega(indicator, valores):
    """Agrega valores mensais (em ordem) pela regra do indicador."""
    valores = [Decimal(v) for v in valores if v is not None]
    if not valores:
        return None
    if indicator.aggregation == Indicator.Aggregation.SOMA:
        return sum(valores)
    if indicator.aggregation == Indicator.Aggregation.MEDIA:
        return sum(valores) / len(valores)
    return valores[-1]


def _meses_no_intervalo(ini, fim):
    cur = _mes_ini(ini)
    while cur <= fim:
        yield cur
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)


def meta_do_bucket(indicator, metas, gran, ini, fim):
    """`metas`: {periodo_mensal: Decimal}."""
    if gran in ("mes", "semestre", "ano"):
        return _agrega(indicator, [metas.get(m) for m in _meses_no_intervalo(ini, fim)])
    # dia / semana com meta diária no ERP (PCMETARCA): exato, sem rateio.
    if indicator.erp_target:
        from erp.targets import meta_do_erp_intervalo

        exata = meta_do_erp_intervalo(indicator.erp_target, indicator.tenant, ini, fim, indicator.erp_filters)
        if exata is not None:
            return exata
    # dia / semana: deriva da meta do mês
    if indicator.aggregation == Indicator.Aggregation.SOMA:
        total, achou = Decimal("0"), False
        for m in _meses_no_intervalo(ini, fim):
            meta = metas.get(m)
            if meta is None:
                continue
            achou = True
            dias_mes = monthrange(m.year, m.month)[1]
            dias_bucket = (min(fim, _mes_fim(m)) - max(ini, m)).days + 1
            total += Decimal(meta) * dias_bucket / dias_mes
        return total if achou else None
    return metas.get(_mes_ini(fim)) if metas.get(_mes_ini(fim)) is not None else metas.get(_mes_ini(ini))


def valor_do_bucket(indicator, valores, gran, ini, fim, hoje):
    """`valores`: {periodo_mensal: Decimal} (só para indicador manual)."""
    if ini > hoje:
        return None
    if indicator.erp_metric:
        from erp.metrics import get_metric

        metric = get_metric(indicator.erp_metric)
        if metric is None:
            return None
        v = metric.compute(indicator.tenant, ini, min(fim, hoje), indicator.erp_filters or {})
        return Decimal(v) if v is not None else None
    if gran in ("dia", "semana"):
        return None  # manual só existe por mês
    return _agrega(indicator, [valores.get(m) for m in _meses_no_intervalo(ini, fim)])


def breakdown(indicator, gran, ate=None, n=None):
    if gran not in GRANULARIDADES:
        raise ValueError("granularidade inválida")
    hoje = date.today()
    ate = ate or hoje
    n = max(1, min(n or PADRAO_N[gran], MAX_N[gran]))
    bks = buckets(gran, ate, n)
    ini_total, fim_total = bks[0][1], bks[-1][2]

    metas = {
        t.period: t.target_value
        for t in IndicatorTarget.objects.filter(indicator=indicator, period__range=(_mes_ini(ini_total), fim_total))
    }
    valores = {}
    if not indicator.erp_metric:
        valores = {
            v.period: v.value
            for v in IndicatorValue.objects.filter(indicator=indicator, period__range=(_mes_ini(ini_total), fim_total))
        }

    q = Decimal(1).scaleb(-indicator.decimals)
    linhas = []
    for label, ini, fim in bks:
        valor = valor_do_bucket(indicator, valores, gran, ini, fim, hoje)
        meta = meta_do_bucket(indicator, metas, gran, ini, fim)
        pct, status = compute_achievement(indicator, valor, meta) if valor is not None else (None, None)
        linhas.append({
            "label": label, "ini": ini, "fim": fim,
            "value": valor.quantize(q) if valor is not None else None,
            "target": Decimal(meta).quantize(q) if meta is not None else None,
            "achievement_pct": pct, "status": status,
            "parcial": ini <= hoje < fim,
        })
    return {
        "granularidade": gran,
        "ate": ate,
        "n": n,
        "fonte": "erp" if indicator.erp_metric else "manual",
        # Dia/semana só fazem sentido com dado do ERP.
        "disponivel": bool(indicator.erp_metric) or gran in ("mes", "semestre", "ano"),
        "periodos": linhas,
    }
