"""Metas vindas do ERP — o elo entre a meta do indicador e o que o WinThor já tem.

O WinThor guarda metas em três lugares que o espelho conhece:

- PCMETARCA (entidade `target_daily`, kind "DIA"): meta DIÁRIA por filial ×
  RCA — é onde a rotina de metas do WinThor grava de verdade. A soma do mês é
  a meta mensal; dia e semana saem exatos.
- PCMETA (entidade `target`): por filial × RCA × mês — venda, positivação,
  mix, margem, pedidos, ticket. Usada quando o cliente mantém essa rotina.
- PCUSUARI.VLVENDAPREV (SalesRep.sales_target): meta de venda do cadastro do
  vendedor. Não varia por mês.

Um Indicator com `erp_target="vlvendaprev"` passa a ter a meta mensal gravada
pela task `sincronizar_metas_erp` (respeitando `erp_filters.branch`), e a
edição manual de metas fica bloqueada — igual ao valor calculado do ERP.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from .metrics import _branch_q, month_bounds
from .models import SalesRep, SalesTarget

D = Decimal
DIA = SalesTarget.KIND_DAILY


@dataclass
class TargetSource:
    key: str
    label: str
    description: str
    entities: list
    compute: Callable          # (tenant, period, filters) -> Decimal | None  (mês)
    daily_field: str = ""      # campo da PCMETARCA que soma por dia (dia/semana exatos)


def _diarias(tenant, ini, fim, filters):
    return SalesTarget.objects.filter(tenant=tenant, kind=DIA, period__range=(ini, fim)).filter(_branch_q(filters))


def _mensais(tenant, period, filters):
    return SalesTarget.objects.filter(tenant=tenant, period=period.replace(day=1)).exclude(kind=DIA).filter(_branch_q(filters))


def _soma_diaria(tenant, ini, fim, filters, campo):
    v = _diarias(tenant, ini, fim, filters).aggregate(v=Sum(campo))["v"]
    return D(v) if v is not None else None


def _soma_mensal(tenant, period, filters, campo):
    v = _mensais(tenant, period, filters).aggregate(v=Sum(campo))["v"]
    return D(v) if v is not None else None


def _soma(tenant, period, filters, campo):
    """Meta do mês: PCMETARCA (soma dos dias) se houver; senão PCMETA."""
    ini, fim = month_bounds(period)
    v = _soma_diaria(tenant, ini, fim, filters, campo)
    return v if v is not None else _soma_mensal(tenant, period, filters, campo)


def _media_ponderada(tenant, period, filters, campo):
    """Média do campo (PCMETA) ponderada pela meta de venda — RCA grande pesa mais."""
    qs = _mensais(tenant, period, filters).filter(**{f"{campo}__isnull": False}, sales_value__gt=0)
    expr = ExpressionWrapper(F(campo) * F("sales_value"), output_field=DecimalField(max_digits=20, decimal_places=4))
    agg = qs.aggregate(p=Sum(expr), w=Sum("sales_value"))
    if not agg["w"]:
        qs = _mensais(tenant, period, filters).filter(**{f"{campo}__isnull": False})
        n = qs.count()
        s = qs.aggregate(v=Sum(campo))["v"]
        return (D(s) / n).quantize(D("0.01")) if n and s is not None else None
    return (D(agg["p"]) / D(agg["w"])).quantize(D("0.01"))


def vlvendaprev(tenant, period, filters=None):
    return _soma(tenant, period, filters, "sales_value")


def clipos(tenant, period, filters=None):
    return _soma(tenant, period, filters, "positivation")


def pedidosprev(tenant, period, filters=None):
    return _soma(tenant, period, filters, "orders")


def margemprev(tenant, period, filters=None):
    return _media_ponderada(tenant, period, filters, "margin_pct")


def vlmediopedido(tenant, period, filters=None):
    return _media_ponderada(tenant, period, filters, "avg_order_value")


def rca_vlvendaprev(tenant, period, filters=None):
    """Soma da meta de venda cadastrada nos vendedores ativos (PCUSUARI)."""
    v = SalesRep.objects.filter(tenant=tenant, is_active=True, sales_target__gt=0).aggregate(v=Sum("sales_target"))["v"]
    return D(v) if v is not None else None


CATALOGO = [
    TargetSource("vlvendaprev", "Meta de venda do WinThor (PCMETARCA / PCMETA)",
                 "Soma da meta de venda dos RCAs no mês, por filial. Com meta diária, dia e semana saem exatos.",
                 ["target_daily", "target"], vlvendaprev, "sales_value"),
    TargetSource("clipos", "Meta de positivação (PCMETARCA / PCMETA)",
                 "Soma dos clientes a positivar no mês.", ["target_daily", "target"], clipos, "positivation"),
    TargetSource("pedidosprev", "Meta de pedidos (PCMETARCA / PCMETA)",
                 "Soma dos pedidos previstos no mês.", ["target_daily", "target"], pedidosprev, "orders"),
    TargetSource("rca_vlvendaprev", "Meta de venda do cadastro do RCA (PCUSUARI)",
                 "Soma da meta mensal cadastrada nos vendedores ativos; igual todo mês.", ["salesrep"], rca_vlvendaprev),
    TargetSource("margemprev", "Meta de margem (PCMETA)",
                 "Margem prevista, ponderada pela meta de venda.", ["target"], margemprev),
    TargetSource("vlmediopedido", "Meta de ticket médio (PCMETA)",
                 "Valor médio de pedido previsto, ponderado pela meta de venda.", ["target"], vlmediopedido),
]
FONTES = {t.key: t for t in CATALOGO}


def get_target_source(key) -> Optional[TargetSource]:
    return FONTES.get(key or "")


def meta_do_erp(key, tenant, period: date, filters=None):
    src = get_target_source(key)
    if src is None:
        return None
    return src.compute(tenant, period, filters or {})


def meta_do_erp_intervalo(key, tenant, ini: date, fim: date, filters=None):
    """Meta exata de um intervalo qualquer (dia, semana) a partir da meta diária.

    None quando a fonte não tem meta diária ou o ERP não tem linhas no intervalo
    — aí o chamador cai no rateio da meta mensal.
    """
    src = get_target_source(key)
    if src is None or not src.daily_field:
        return None
    return _soma_diaria(tenant, ini, fim, filters or {}, src.daily_field)


def catalogo_payload():
    return [
        {"key": t.key, "label": t.label, "description": t.description, "entities": t.entities, "diaria": bool(t.daily_field)}
        for t in CATALOGO
    ]
