"""Catálogo de métricas do ERP — o elo entre indicador e dado real.

Um Indicator com `erp_metric="faturamento"` deixa de ser lançado à mão: a cada
ciclo a task `calcular_indicadores_erp` chama a métrica para cada mês do ano e
grava IndicatorValue(source=agent). O gestor só define a meta.

Cada métrica declara o que precisa para o catálogo e a UI:
  key, label, unit, polarity, aggregation, description, entities (o que o agente
  precisa ter coletado), compute(tenant, first_day, last_day, filters) -> Decimal|None.

`filters` aceita {"branch": "<CODFILIAL>"} — filial é a dimensão que uma
distribuidora com varejo mais usa (CD × lojas).
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Optional

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum

from . import regras
from .models import (
    BankAccount,
    CashMovement,
    Customer,
    DeliveryLoad,
    Employee,
    FinancialSnapshot,
    FinancialTitle,
    Order,
    Product,
    PurchaseInvoice,
    SalesInvoice,
    SalesInvoiceItem,
    StockBalance,
)

D = Decimal
ZERO = D("0")


@dataclass
class Metric:
    key: str
    label: str
    unit: str
    polarity: str            # maior_melhor | menor_melhor
    aggregation: str         # soma | media | ultimo  (como acumular no ano)
    description: str
    entities: list
    compute: Callable
    group: str = "Vendas"
    decimals: int = 2
    tags: list = field(default_factory=list)


def _branch_q(filters, path="branch"):
    """`branch` aceita um código ("10"), vários separados por vírgula ("11,12")
    ou uma lista (["11", "12"]) — as lojas de um atacarejo, por exemplo."""
    code = (filters or {}).get("branch")
    if not code:
        return Q()
    if isinstance(code, str):
        code = [c.strip() for c in code.split(",") if c.strip()]
    codes = [str(c) for c in code]
    if not codes:
        return Q()
    if len(codes) == 1:
        return Q(**{f"{path}__code": codes[0]})
    return Q(**{f"{path}__code__in": codes})


def _sum(qs, expr):
    v = qs.aggregate(v=Sum(expr))["v"]
    return D(v) if v is not None else None


def _pct(num, den):
    if num is None or not den:
        return None
    return (D(num) / D(den) * 100).quantize(D("0.01"))


def _money(v):
    return D(v).quantize(D("0.01")) if v is not None else None


# --- Vendas -----------------------------------------------------------------

def notas_do_periodo(tenant, ini, fim, filters):
    return SalesInvoice.objects.filter(
        tenant=tenant, issued_at__range=(ini, fim)
    ).filter(regras.filtro_notas_faturadas()).filter(_branch_q(filters))


def faturamento(tenant, ini, fim, filters=None):
    return _money(_sum(notas_do_periodo(tenant, ini, fim, filters), "total"))


def qtd_notas(tenant, ini, fim, filters=None):
    return D(notas_do_periodo(tenant, ini, fim, filters).count())


def ticket_medio(tenant, ini, fim, filters=None):
    qs = notas_do_periodo(tenant, ini, fim, filters)
    n = qs.count()
    total = _sum(qs, "total")
    return _money(total / n) if n and total is not None else None


def positivacao(tenant, ini, fim, filters=None):
    """Clientes distintos que compraram no período."""
    return D(
        notas_do_periodo(tenant, ini, fim, filters)
        .filter(customer__isnull=False)
        .values("customer").distinct().count()
    )


def clientes_ativos(tenant, ini, fim, filters=None):
    """Clientes com compra nos últimos 90 dias (contados até o fim do período)."""
    return D(
        Customer.objects.filter(
            tenant=tenant, blocked=False,
            last_purchase_at__gte=fim - timedelta(days=90), last_purchase_at__lte=fim,
        ).count()
    )


def novos_clientes(tenant, ini, fim, filters=None):
    """Clientes cuja PRIMEIRA compra caiu no período (DTPRIMCOMPRA)."""
    return D(Customer.objects.filter(tenant=tenant, first_purchase_at__range=(ini, fim)).count())


def churn_clientes_pct(tenant, ini, fim, filters=None):
    """% dos clientes que compraram nos 90 dias ANTERIORES e não compraram nos 90 até o fim."""
    janela_atual_ini = fim - timedelta(days=90)
    janela_ant_ini = janela_atual_ini - timedelta(days=90)
    base = set(
        SalesInvoice.objects.filter(tenant=tenant, issued_at__range=(janela_ant_ini, janela_atual_ini - timedelta(days=1)))
        .filter(regras.filtro_notas_faturadas()).filter(_branch_q(filters))
        .values_list("customer_id", flat=True)
    )
    base.discard(None)
    if not base:
        return None
    ativos = set(
        SalesInvoice.objects.filter(tenant=tenant, issued_at__range=(janela_atual_ini, fim), customer_id__in=base)
        .filter(regras.filtro_notas_faturadas()).filter(_branch_q(filters))
        .values_list("customer_id", flat=True)
    )
    return _pct(len(base - ativos), len(base))


def _itens_venda(tenant, ini, fim, filters):
    return SalesInvoiceItem.objects.filter(
        tenant=tenant, moved_at__range=(ini, fim), operation__in=regras.OPERACOES_VENDA,
    ).filter(_branch_q(filters))


_VALOR = ExpressionWrapper(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=18, decimal_places=4))
_CUSTO = ExpressionWrapper(F("quantity") * F("cost"), output_field=DecimalField(max_digits=18, decimal_places=4))


def margem_bruta_pct(tenant, ini, fim, filters=None):
    qs = _itens_venda(tenant, ini, fim, filters).filter(cost__isnull=False)
    agg = qs.aggregate(v=Sum(_VALOR), c=Sum(_CUSTO))
    if not agg["v"]:
        return None
    return _pct(D(agg["v"]) - D(agg["c"] or 0), agg["v"])


def cmv(tenant, ini, fim, filters=None):
    return _money(_sum(_itens_venda(tenant, ini, fim, filters).filter(cost__isnull=False), _CUSTO))


def desconto_medio_pct(tenant, ini, fim, filters=None):
    """Desconto praticado sobre a tabela: 1 - (preço praticado / tabela)."""
    qs = _itens_venda(tenant, ini, fim, filters).filter(table_price__gt=0)
    tab = ExpressionWrapper(F("quantity") * F("table_price"), output_field=DecimalField(max_digits=18, decimal_places=4))
    agg = qs.aggregate(v=Sum(_VALOR), t=Sum(tab))
    if not agg["t"]:
        return None
    return _pct(D(agg["t"]) - D(agg["v"] or 0), agg["t"])


def devolucoes_pct(tenant, ini, fim, filters=None):
    dev = SalesInvoiceItem.objects.filter(
        tenant=tenant, moved_at__range=(ini, fim), operation__in=regras.OPERACOES_DEVOLUCAO,
    ).filter(_branch_q(filters))
    vendas = _sum(_itens_venda(tenant, ini, fim, filters), _VALOR)
    return _pct(_sum(dev, _VALOR) or ZERO, vendas)


def bonificacao_pct(tenant, ini, fim, filters=None):
    bon = SalesInvoice.objects.filter(tenant=tenant, issued_at__range=(ini, fim)).filter(
        regras.filtro_bonificacoes()
    ).filter(_branch_q(filters))
    return _pct(_sum(bon, "total") or ZERO, faturamento(tenant, ini, fim, filters))


def mix_skus(tenant, ini, fim, filters=None):
    """SKUs distintos vendidos no período."""
    return D(_itens_venda(tenant, ini, fim, filters).values("product").distinct().count())


def carteira_pedidos(tenant, ini, fim, filters=None):
    """Valor em pedidos pendentes (não faturados nem cancelados) no fim do período."""
    qs = Order.objects.filter(tenant=tenant, status=Order.Status.PENDING, order_date__lte=fim).filter(_branch_q(filters))
    return _money(_sum(qs, "total") or ZERO)


def corte_pct(tenant, ini, fim, filters=None):
    """% de pedidos do período com corte (item entregue a menos)."""
    qs = Order.objects.filter(tenant=tenant, order_date__range=(ini, fim)).exclude(status=Order.Status.CANCELED).filter(_branch_q(filters))
    n = qs.count()
    return _pct(qs.filter(erp_cut_qty__gt=0).count(), n) if n else None


def conversao_pedido_nota_pct(tenant, ini, fim, filters=None):
    qs = Order.objects.filter(tenant=tenant, order_date__range=(ini, fim)).filter(_branch_q(filters))
    n = qs.count()
    return _pct(qs.filter(status=Order.Status.SHIPPED).count(), n) if n else None


# --- Financeiro --------------------------------------------------------------

def _receber(tenant, filters):
    return FinancialTitle.objects.filter(tenant=tenant, kind=FinancialTitle.Kind.RECEIVABLE).filter(_branch_q(filters))


def _pagar(tenant, filters):
    return FinancialTitle.objects.filter(tenant=tenant, kind=FinancialTitle.Kind.PAYABLE).filter(_branch_q(filters))


def a_receber_aberto(tenant, ini, fim, filters=None):
    return _money(_sum(_receber(tenant, filters).filter(status="open"), "amount") or ZERO)


def a_receber_vencido(tenant, ini, fim, filters=None):
    return _money(_sum(_receber(tenant, filters).filter(status="open", due_date__lt=fim), "amount") or ZERO)


def inadimplencia_pct(tenant, ini, fim, filters=None):
    """Vencido há mais de 30 dias sobre o total em aberto."""
    aberto = _sum(_receber(tenant, filters).filter(status="open"), "amount")
    vencido = _sum(_receber(tenant, filters).filter(status="open", due_date__lt=fim - timedelta(days=30)), "amount") or ZERO
    return _pct(vencido, aberto)


def recebido(tenant, ini, fim, filters=None):
    return _money(_sum(_receber(tenant, filters).filter(status="paid", paid_at__range=(ini, fim)), "amount_paid") or ZERO)


def prazo_medio_recebimento(tenant, ini, fim, filters=None):
    """Dias entre emissão e pagamento, ponderado pelo valor (títulos pagos no período)."""
    qs = _receber(tenant, filters).filter(status="paid", paid_at__range=(ini, fim), issue_date__isnull=False)
    total, soma = ZERO, ZERO
    for t in qs.only("amount", "issue_date", "paid_at"):
        dias = (t.paid_at - t.issue_date).days
        total += t.amount or ZERO
        soma += (t.amount or ZERO) * dias
    return (soma / total).quantize(D("0.1")) if total else None


def a_pagar_aberto(tenant, ini, fim, filters=None):
    return _money(_sum(_pagar(tenant, filters).filter(status="open"), "amount") or ZERO)


def a_pagar_vencido(tenant, ini, fim, filters=None):
    return _money(_sum(_pagar(tenant, filters).filter(status="open", due_date__lt=fim), "amount") or ZERO)


def despesas_pagas(tenant, ini, fim, filters=None):
    return _money(_sum(_pagar(tenant, filters).filter(status="paid", paid_at__range=(ini, fim)), "amount_paid") or ZERO)


def despesas_competencia(tenant, ini, fim, filters=None):
    """Despesas pela competência (DTCOMPETENCIA), pagas ou não — visão de DRE."""
    return _money(_sum(_pagar(tenant, filters).exclude(status="canceled").filter(accrual_date__range=(ini, fim)), "amount") or ZERO)


def folha_pct_faturamento(tenant, ini, fim, filters=None):
    """Salários (TIPOSERVICO 30) sobre o faturamento."""
    folha = _sum(_pagar(tenant, filters).exclude(status="canceled").filter(tax_type="30", accrual_date__range=(ini, fim)), "amount")
    return _pct(folha, faturamento(tenant, ini, fim, filters))


def saldo_caixa(tenant, ini, fim, filters=None):
    """Caixa + bancos + aplicações na última fotografia do período (PCFINANC); fallback PCBANCO."""
    snaps = FinancialSnapshot.objects.filter(tenant=tenant, date__lte=fim).filter(_branch_q(filters))
    ultimo = snaps.order_by("-date").values_list("date", flat=True).first()
    if ultimo:
        agg = snaps.filter(date=ultimo).aggregate(b=Sum("bank_balance"), c=Sum("cash_balance"), a=Sum("investments"))
        return _money(D(agg["b"] or 0) + D(agg["c"] or 0) + D(agg["a"] or 0))
    saldo = _sum(BankAccount.objects.filter(tenant=tenant).filter(_branch_q(filters)), "balance")
    return _money(saldo) if saldo is not None else None


def geracao_caixa(tenant, ini, fim, filters=None):
    """Entradas menos saídas do extrato (PCMOVCR) no período."""
    qs = CashMovement.objects.filter(tenant=tenant, moved_at__range=(ini, fim)).filter(_branch_q(filters))
    ent = _sum(qs.filter(kind="D"), "amount") or ZERO
    sai = _sum(qs.filter(kind="C"), "amount") or ZERO
    if not qs.exists():
        return None
    return _money(ent - sai)


# --- Estoque e compras -------------------------------------------------------

def _estoque(tenant, filters):
    return StockBalance.objects.filter(tenant=tenant, product__is_active=True).filter(_branch_q(filters))


def estoque_valor(tenant, ini, fim, filters=None):
    expr = ExpressionWrapper(F("quantity") * F("avg_cost"), output_field=DecimalField(max_digits=18, decimal_places=4))
    return _money(_sum(_estoque(tenant, filters).filter(avg_cost__isnull=False, quantity__gt=0), expr) or ZERO)


def ruptura_pct(tenant, ini, fim, filters=None):
    """% de itens ativos com giro (vendeu no mês) e disponível <= 0."""
    qs = _estoque(tenant, filters).filter(qty_sold_month__gt=0)
    n = qs.count()
    if not n:
        return None
    zerados = qs.filter(quantity__lte=F("reserved") + F("blocked")).count()
    return _pct(zerados, n)


def cobertura_estoque_dias(tenant, ini, fim, filters=None):
    """Dias de estoque: saldo disponível / giro diário (PCEST.QTGIRODIA), ponderado por custo."""
    qs = _estoque(tenant, filters).filter(daily_turnover__gt=0, avg_cost__isnull=False, quantity__gt=0)
    valor, dias_valor = ZERO, ZERO
    for s in qs.only("quantity", "reserved", "blocked", "daily_turnover", "avg_cost"):
        disp = (s.quantity or ZERO) - (s.reserved or ZERO) - (s.blocked or ZERO)
        if disp <= 0:
            continue
        v = disp * (s.avg_cost or ZERO)
        valor += v
        dias_valor += v * (disp / s.daily_turnover)
    return (dias_valor / valor).quantize(D("0.1")) if valor else None


def giro_estoque(tenant, ini, fim, filters=None):
    """CMV do período / estoque médio (aprox. pelo saldo atual)."""
    custo = cmv(tenant, ini, fim, filters)
    est = estoque_valor(tenant, ini, fim, filters)
    return (custo / est).quantize(D("0.01")) if custo is not None and est else None


def compras_valor(tenant, ini, fim, filters=None):
    return _money(_sum(PurchaseInvoice.objects.filter(tenant=tenant, entry_date__range=(ini, fim)).filter(_branch_q(filters)), "total") or ZERO)


def venda_perdida_qtd(tenant, ini, fim, filters=None):
    """Unidades que o ERP registrou como venda perdida por falta (PCEST.QTVENDAPERDIDA)."""
    v = _sum(_estoque(tenant, filters), "qty_lost_sales")
    return D(v).quantize(D("0.1")) if v is not None else None


# --- Logística ---------------------------------------------------------------

def _cargas(tenant, ini, fim, filters):
    return DeliveryLoad.objects.filter(tenant=tenant, departure_date__range=(ini, fim)).exclude(
        status=DeliveryLoad.Status.CANCELED
    ).filter(_branch_q(filters))


def cargas_expedidas(tenant, ini, fim, filters=None):
    return D(_cargas(tenant, ini, fim, filters).count())


def frete_pct_faturamento(tenant, ini, fim, filters=None):
    frete = _sum(_cargas(tenant, ini, fim, filters), "freight")
    return _pct(frete, faturamento(tenant, ini, fim, filters))


def peso_entregue_ton(tenant, ini, fim, filters=None):
    v = _sum(_cargas(tenant, ini, fim, filters), "total_weight")
    return (D(v) / 1000).quantize(D("0.01")) if v is not None else None


def notas_por_carga(tenant, ini, fim, filters=None):
    qs = _cargas(tenant, ini, fim, filters)
    n = qs.count()
    notas = _sum(qs, "num_invoices")
    return (D(notas) / n).quantize(D("0.1")) if n and notas is not None else None


# --- Pessoas ------------------------------------------------------------------

def headcount(tenant, ini, fim, filters=None):
    return D(
        Employee.objects.filter(tenant=tenant, admission_date__lte=fim)
        .filter(Q(dismissal_date__isnull=True) | Q(dismissal_date__gt=fim))
        .filter(_branch_q(filters)).count()
    )


def turnover_pct(tenant, ini, fim, filters=None):
    """(admissões + demissões) / 2 sobre o headcount médio do período."""
    qs = Employee.objects.filter(tenant=tenant).filter(_branch_q(filters))
    adm = qs.filter(admission_date__range=(ini, fim)).count()
    dem = qs.filter(dismissal_date__range=(ini, fim)).count()
    hc = headcount(tenant, ini, fim, filters)
    if not hc:
        return None
    return _pct(D((adm + dem) / 2), hc)


def desligamentos(tenant, ini, fim, filters=None):
    return D(Employee.objects.filter(tenant=tenant, dismissal_date__range=(ini, fim)).filter(_branch_q(filters)).count())


# --- Vendas: pedidos, RCAs, concentração --------------------------------------
# Regras vistas no WinThor (extrator/estudos): faturamento na PCNFSAID; pedido
# em PCPEDC com POSICAO L/M/B/P/F/C; venda perdida em PCFALTA e PCPEDI.QTFALTA;
# positivação = clientes distintos faturados (PCSIS111).

def _pedidos(tenant, ini, fim, filters):
    return Order.objects.filter(tenant=tenant, order_date__range=(ini, fim)).exclude(
        status=Order.Status.CANCELED
    ).filter(_branch_q(filters))


def qtd_pedidos(tenant, ini, fim, filters=None):
    return D(_pedidos(tenant, ini, fim, filters).count())


def pedido_medio(tenant, ini, fim, filters=None):
    qs = _pedidos(tenant, ini, fim, filters)
    n = qs.count()
    total = _sum(qs, "total")
    return _money(total / n) if n and total is not None else None


def pedidos_cancelados_pct(tenant, ini, fim, filters=None):
    qs = Order.objects.filter(tenant=tenant, order_date__range=(ini, fim)).filter(_branch_q(filters))
    n = qs.count()
    return _pct(qs.filter(status=Order.Status.CANCELED).count(), n) if n else None


def rcas_ativos(tenant, ini, fim, filters=None):
    """Vendedores com pelo menos uma nota faturada no período."""
    return D(notas_do_periodo(tenant, ini, fim, filters).filter(sales_rep__isnull=False).values("sales_rep").distinct().count())


def venda_media_por_rca(tenant, ini, fim, filters=None):
    n = rcas_ativos(tenant, ini, fim, filters)
    fat = faturamento(tenant, ini, fim, filters)
    return _money(fat / n) if n and fat is not None else None


def clientes_por_rca(tenant, ini, fim, filters=None):
    n = rcas_ativos(tenant, ini, fim, filters)
    pos = positivacao(tenant, ini, fim, filters)
    return (pos / n).quantize(D("0.1")) if n else None


def notas_por_cliente(tenant, ini, fim, filters=None):
    pos = positivacao(tenant, ini, fim, filters)
    n = qtd_notas(tenant, ini, fim, filters)
    return (n / pos).quantize(D("0.01")) if pos else None


def itens_por_nota(tenant, ini, fim, filters=None):
    itens = _itens_venda(tenant, ini, fim, filters).count()
    n = qtd_notas(tenant, ini, fim, filters)
    return (D(itens) / n).quantize(D("0.1")) if n else None


def concentracao_top10_clientes_pct(tenant, ini, fim, filters=None):
    """Fatia do faturamento nos 10 maiores clientes do período."""
    qs = notas_do_periodo(tenant, ini, fim, filters).filter(customer__isnull=False)
    total = _sum(qs, "total")
    if not total:
        return None
    top = qs.values("customer").annotate(v=Sum("total")).order_by("-v")[:10]
    return _pct(sum(D(r["v"]) for r in top), total)


def concentracao_top_rca_pct(tenant, ini, fim, filters=None):
    qs = notas_do_periodo(tenant, ini, fim, filters).filter(sales_rep__isnull=False)
    total = _sum(qs, "total")
    if not total:
        return None
    top = qs.values("sales_rep").annotate(v=Sum("total")).order_by("-v")[:1]
    return _pct(D(top[0]["v"]), total) if top else None


def crescimento_faturamento_yoy_pct(tenant, ini, fim, filters=None):
    """Faturamento do período contra o mesmo período do ano anterior."""
    atual = faturamento(tenant, ini, fim, filters)
    try:
        ini_a, fim_a = ini.replace(year=ini.year - 1), fim.replace(year=fim.year - 1)
    except ValueError:  # 29/02
        ini_a, fim_a = ini.replace(year=ini.year - 1, day=28), fim.replace(year=fim.year - 1, day=28)
    anterior = faturamento(tenant, ini_a, fim_a, filters)
    if atual is None or not anterior:
        return None
    return ((atual - anterior) / anterior * 100).quantize(D("0.01"))


def venda_perdida_corte(tenant, ini, fim, filters=None):
    """Quantidade cortada nos pedidos do período (PCPEDI.QTFALTA agregada em PCPEDC)."""
    v = _sum(_pedidos(tenant, ini, fim, filters).filter(erp_cut_qty__gt=0), "erp_cut_qty")
    return D(v).quantize(D("0.1")) if v is not None else None


def pedidos_faturados_no_dia_pct(tenant, ini, fim, filters=None):
    """% dos pedidos faturados no mesmo dia em que foram digitados."""
    qs = _pedidos(tenant, ini, fim, filters).filter(status=Order.Status.SHIPPED, invoiced_at__isnull=False)
    n = qs.count()
    return _pct(qs.filter(invoiced_at=F("order_date")).count(), n) if n else None


def lucro_bruto(tenant, ini, fim, filters=None):
    qs = _itens_venda(tenant, ini, fim, filters).filter(cost__isnull=False)
    agg = qs.aggregate(v=Sum(_VALOR), c=Sum(_CUSTO))
    if agg["v"] is None:
        return None
    return _money(D(agg["v"]) - D(agg["c"] or 0))


def markup_pct(tenant, ini, fim, filters=None):
    qs = _itens_venda(tenant, ini, fim, filters).filter(cost__isnull=False)
    agg = qs.aggregate(v=Sum(_VALOR), c=Sum(_CUSTO))
    if not agg["c"]:
        return None
    return _pct(D(agg["v"] or 0) - D(agg["c"]), agg["c"])


def preco_medio_item(tenant, ini, fim, filters=None):
    qs = _itens_venda(tenant, ini, fim, filters)
    agg = qs.aggregate(v=Sum(_VALOR), q=Sum("quantity"))
    return _money(D(agg["v"]) / D(agg["q"])) if agg["q"] else None


# --- Financeiro: aging, prazos, liquidez --------------------------------------

def a_receber_vencido_60_pct(tenant, ini, fim, filters=None):
    """Vencido há mais de 60 dias sobre o total em aberto (carteira envelhecida)."""
    aberto = _sum(_receber(tenant, filters).filter(status="open"), "amount")
    venc = _sum(_receber(tenant, filters).filter(status="open", due_date__lt=fim - timedelta(days=60)), "amount") or ZERO
    return _pct(venc, aberto)


def titulos_pagos_no_prazo_pct(tenant, ini, fim, filters=None):
    """% dos títulos baixados no mês que foram pagos até o vencimento."""
    qs = _receber(tenant, filters).filter(status="paid", paid_at__range=(ini, fim), due_date__isnull=False)
    n = qs.count()
    return _pct(qs.filter(paid_at__lte=F("due_date")).count(), n) if n else None


def atraso_medio_recebimento_dias(tenant, ini, fim, filters=None):
    """Dias além do vencimento nos títulos pagos com atraso no mês (ponderado por valor)."""
    qs = _receber(tenant, filters).filter(status="paid", paid_at__range=(ini, fim), due_date__isnull=False, paid_at__gt=F("due_date"))
    total, soma = ZERO, ZERO
    for t in qs.only("amount", "due_date", "paid_at"):
        total += t.amount or ZERO
        soma += (t.amount or ZERO) * (t.paid_at - t.due_date).days
    return (soma / total).quantize(D("0.1")) if total else None


def multa_juros_recebidos(tenant, ini, fim, filters=None):
    return _money(_sum(_receber(tenant, filters).filter(status="paid", paid_at__range=(ini, fim)), "fine") or ZERO)


def prazo_medio_pagamento(tenant, ini, fim, filters=None):
    """Dias entre emissão e pagamento das contas a pagar baixadas no mês (ponderado)."""
    qs = _pagar(tenant, filters).filter(status="paid", paid_at__range=(ini, fim), issue_date__isnull=False)
    total, soma = ZERO, ZERO
    for t in qs.only("amount", "issue_date", "paid_at"):
        total += t.amount or ZERO
        soma += (t.amount or ZERO) * (t.paid_at - t.issue_date).days
    return (soma / total).quantize(D("0.1")) if total else None


def a_pagar_vencido_pct(tenant, ini, fim, filters=None):
    aberto = _sum(_pagar(tenant, filters).filter(status="open"), "amount")
    venc = _sum(_pagar(tenant, filters).filter(status="open", due_date__lt=fim), "amount") or ZERO
    return _pct(venc, aberto)


def a_pagar_proximos_30_dias(tenant, ini, fim, filters=None):
    return _money(_sum(_pagar(tenant, filters).filter(status="open", due_date__range=(fim, fim + timedelta(days=30))), "amount") or ZERO)


def a_receber_proximos_30_dias(tenant, ini, fim, filters=None):
    return _money(_sum(_receber(tenant, filters).filter(status="open", due_date__range=(fim, fim + timedelta(days=30))), "amount") or ZERO)


def liquidez_cr_cp(tenant, ini, fim, filters=None):
    """Contas a receber em aberto ÷ contas a pagar em aberto."""
    cr = a_receber_aberto(tenant, ini, fim, filters)
    cp = a_pagar_aberto(tenant, ini, fim, filters)
    return (cr / cp).quantize(D("0.01")) if cp else None


def dso_dias(tenant, ini, fim, filters=None):
    """Days Sales Outstanding: a receber em aberto ÷ faturamento dos últimos 90 dias × 90."""
    cr = a_receber_aberto(tenant, ini, fim, filters)
    fat90 = faturamento(tenant, fim - timedelta(days=89), fim, filters)
    return (cr / fat90 * 90).quantize(D("0.1")) if fat90 else None


def despesas_pct_faturamento(tenant, ini, fim, filters=None):
    return _pct(despesas_competencia(tenant, ini, fim, filters), faturamento(tenant, ini, fim, filters))


def resultado_operacional(tenant, ini, fim, filters=None):
    """Lucro bruto dos itens − despesas por competência (aproximação de resultado)."""
    lb = lucro_bruto(tenant, ini, fim, filters)
    desp = despesas_competencia(tenant, ini, fim, filters)
    return _money(lb - desp) if lb is not None else None


def resultado_operacional_pct(tenant, ini, fim, filters=None):
    return _pct(resultado_operacional(tenant, ini, fim, filters), faturamento(tenant, ini, fim, filters))


def entradas_caixa(tenant, ini, fim, filters=None):
    qs = CashMovement.objects.filter(tenant=tenant, moved_at__range=(ini, fim), kind="D").filter(_branch_q(filters))
    v = _sum(qs, "amount")
    return _money(v) if v is not None else None


def saidas_caixa(tenant, ini, fim, filters=None):
    qs = CashMovement.objects.filter(tenant=tenant, moved_at__range=(ini, fim), kind="C").filter(_branch_q(filters))
    v = _sum(qs, "amount")
    return _money(v) if v is not None else None


def _ultima_foto(tenant, fim, filters):
    snaps = FinancialSnapshot.objects.filter(tenant=tenant, date__lte=fim).filter(_branch_q(filters))
    ultimo = snaps.order_by("-date").values_list("date", flat=True).first()
    return snaps.filter(date=ultimo) if ultimo else None


def posicao_liquida_financeira(tenant, ini, fim, filters=None):
    """SALDOREAL da PCFINANC (caixa + bancos + CR − CP) na última fotografia."""
    foto = _ultima_foto(tenant, fim, filters)
    if foto is None:
        return None
    v = foto.aggregate(v=Sum("net_position"))["v"]
    return _money(v) if v is not None else None


def estoque_financeiro_foto(tenant, ini, fim, filters=None):
    foto = _ultima_foto(tenant, fim, filters)
    if foto is None:
        return None
    v = foto.aggregate(v=Sum("stock_value"))["v"]
    return _money(v) if v is not None else None


# --- Estoque: capital parado, excesso, cobertura ------------------------------

_VALOR_EST = ExpressionWrapper(F("quantity") * F("avg_cost"), output_field=DecimalField(max_digits=18, decimal_places=4))


def capital_parado(tenant, ini, fim, filters=None):
    """Estoque a custo dos itens sem venda no mês (QTVENDMES = 0)."""
    qs = _estoque(tenant, filters).filter(quantity__gt=0, avg_cost__isnull=False).filter(Q(qty_sold_month__isnull=True) | Q(qty_sold_month__lte=0))
    return _money(_sum(qs, _VALOR_EST) or ZERO)


def capital_parado_pct(tenant, ini, fim, filters=None):
    return _pct(capital_parado(tenant, ini, fim, filters), estoque_valor(tenant, ini, fim, filters))


def itens_sem_giro_pct(tenant, ini, fim, filters=None):
    qs = _estoque(tenant, filters).filter(quantity__gt=0)
    n = qs.count()
    return _pct(qs.filter(Q(qty_sold_month__isnull=True) | Q(qty_sold_month__lte=0)).count(), n) if n else None


def excesso_estoque(tenant, ini, fim, filters=None):
    """Valor acima do estoque máximo (ESTMAX) por produto × filial."""
    qs = _estoque(tenant, filters).filter(max_stock__gt=0, quantity__gt=F("max_stock"), avg_cost__isnull=False)
    expr = ExpressionWrapper((F("quantity") - F("max_stock")) * F("avg_cost"), output_field=DecimalField(max_digits=18, decimal_places=4))
    return _money(_sum(qs, expr) or ZERO)


def abaixo_minimo_pct(tenant, ini, fim, filters=None):
    """% dos itens com estoque mínimo definido que estão abaixo dele (gatilho de reposição)."""
    qs = _estoque(tenant, filters).filter(min_stock__gt=0)
    n = qs.count()
    return _pct(qs.filter(quantity__lt=F("min_stock")).count(), n) if n else None


def skus_com_estoque(tenant, ini, fim, filters=None):
    return D(_estoque(tenant, filters).filter(quantity__gt=0).values("product").distinct().count())


def estoque_bloqueado(tenant, ini, fim, filters=None):
    qs = _estoque(tenant, filters).filter(blocked__gt=0, avg_cost__isnull=False)
    expr = ExpressionWrapper(F("blocked") * F("avg_cost"), output_field=DecimalField(max_digits=18, decimal_places=4))
    return _money(_sum(qs, expr) or ZERO)


# --- Compras -------------------------------------------------------------------

def _compras(tenant, ini, fim, filters):
    return PurchaseInvoice.objects.filter(tenant=tenant, entry_date__range=(ini, fim)).filter(_branch_q(filters))


def qtd_notas_entrada(tenant, ini, fim, filters=None):
    return D(_compras(tenant, ini, fim, filters).count())


def fornecedores_ativos(tenant, ini, fim, filters=None):
    return D(_compras(tenant, ini, fim, filters).filter(supplier__isnull=False).values("supplier").distinct().count())


def compra_media_por_nota(tenant, ini, fim, filters=None):
    qs = _compras(tenant, ini, fim, filters)
    n = qs.count()
    total = _sum(qs, "total")
    return _money(total / n) if n and total is not None else None


def compras_pct_faturamento(tenant, ini, fim, filters=None):
    return _pct(compras_valor(tenant, ini, fim, filters), faturamento(tenant, ini, fim, filters))


def concentracao_top5_fornecedores_pct(tenant, ini, fim, filters=None):
    qs = _compras(tenant, ini, fim, filters).filter(supplier__isnull=False)
    total = _sum(qs, "total")
    if not total:
        return None
    top = qs.values("supplier").annotate(v=Sum("total")).order_by("-v")[:5]
    return _pct(sum(D(r["v"]) for r in top), total)


def frete_compras_pct(tenant, ini, fim, filters=None):
    qs = _compras(tenant, ini, fim, filters)
    return _pct(_sum(qs, "freight") or ZERO, _sum(qs, "total"))


# --- Logística -----------------------------------------------------------------

def valor_medio_por_carga(tenant, ini, fim, filters=None):
    qs = _cargas(tenant, ini, fim, filters)
    n = qs.count()
    total = _sum(qs, "total_value")
    return _money(total / n) if n and total is not None else None


def peso_medio_por_carga_kg(tenant, ini, fim, filters=None):
    qs = _cargas(tenant, ini, fim, filters)
    n = qs.count()
    peso = _sum(qs, "total_weight")
    return (D(peso) / n).quantize(D("0.1")) if n and peso is not None else None


def tempo_medio_rota_dias(tenant, ini, fim, filters=None):
    """Dias entre saída e retorno das cargas que voltaram no período."""
    qs = DeliveryLoad.objects.filter(tenant=tenant, return_date__range=(ini, fim), departure_date__isnull=False).filter(_branch_q(filters))
    n, soma = 0, 0
    for c in qs.only("departure_date", "return_date"):
        n += 1
        soma += (c.return_date - c.departure_date).days
    return (D(soma) / n).quantize(D("0.1")) if n else None


def cargas_em_rota(tenant, ini, fim, filters=None):
    """Cargas que saíram e ainda não retornaram no fim do período."""
    return D(DeliveryLoad.objects.filter(tenant=tenant, departure_date__lte=fim, return_date__isnull=True).exclude(
        status=DeliveryLoad.Status.CANCELED).filter(_branch_q(filters)).count())


def cargas_canceladas_pct(tenant, ini, fim, filters=None):
    qs = DeliveryLoad.objects.filter(tenant=tenant, departure_date__range=(ini, fim)).filter(_branch_q(filters))
    n = qs.count()
    return _pct(qs.filter(status=DeliveryLoad.Status.CANCELED).count(), n) if n else None


def custo_frete_por_kg(tenant, ini, fim, filters=None):
    qs = _cargas(tenant, ini, fim, filters)
    frete, peso = _sum(qs, "freight"), _sum(qs, "total_weight")
    return (D(frete) / D(peso)).quantize(D("0.0001")) if frete is not None and peso else None


def custo_frete_por_nota(tenant, ini, fim, filters=None):
    qs = _cargas(tenant, ini, fim, filters)
    frete, notas = _sum(qs, "freight"), _sum(qs, "num_invoices")
    return _money(D(frete) / D(notas)) if frete is not None and notas else None


# --- Fiscal (a partir da NF de saída espelhada) -------------------------------

def _notas_todas(tenant, ini, fim, filters):
    return SalesInvoice.objects.filter(tenant=tenant, issued_at__range=(ini, fim)).filter(_branch_q(filters))


def nfe_autorizadas_pct(tenant, ini, fim, filters=None):
    """% das NF-e do período com SITUACAONFE = 100 (autorizada na SEFAZ)."""
    qs = _notas_todas(tenant, ini, fim, filters).exclude(nfe_status="")
    n = qs.count()
    return _pct(qs.filter(nfe_status="100").count(), n) if n else None


def notas_canceladas_pct(tenant, ini, fim, filters=None):
    qs = _notas_todas(tenant, ini, fim, filters)
    n = qs.count()
    return _pct(qs.filter(canceled_at__isnull=False).count(), n) if n else None


def icms_pct_faturamento(tenant, ini, fim, filters=None):
    qs = notas_do_periodo(tenant, ini, fim, filters)
    return _pct(_sum(qs, "icms_value") or ZERO, _sum(qs, "total"))


def st_pct_faturamento(tenant, ini, fim, filters=None):
    qs = notas_do_periodo(tenant, ini, fim, filters)
    return _pct(_sum(qs, "icms_st_value") or ZERO, _sum(qs, "total"))


def ipi_pct_faturamento(tenant, ini, fim, filters=None):
    qs = notas_do_periodo(tenant, ini, fim, filters)
    return _pct(_sum(qs, "ipi_value") or ZERO, _sum(qs, "total"))


def carga_tributaria_pct(tenant, ini, fim, filters=None):
    qs = notas_do_periodo(tenant, ini, fim, filters)
    trib = (_sum(qs, "icms_value") or ZERO) + (_sum(qs, "icms_st_value") or ZERO) + (_sum(qs, "ipi_value") or ZERO)
    return _pct(trib, _sum(qs, "total"))


def notas_por_dia_util(tenant, ini, fim, filters=None):
    dias = sum(1 for i in range((fim - ini).days + 1) if (ini + timedelta(days=i)).weekday() < 5) or 1
    return (qtd_notas(tenant, ini, fim, filters) / dias).quantize(D("0.1"))


# --- Clientes -------------------------------------------------------------------

def base_clientes(tenant, ini, fim, filters=None):
    return D(Customer.objects.filter(tenant=tenant, blocked=False).count())


def clientes_bloqueados_pct(tenant, ini, fim, filters=None):
    qs = Customer.objects.filter(tenant=tenant)
    n = qs.count()
    return _pct(qs.filter(blocked=True).count(), n) if n else None


def clientes_inativos_90_pct(tenant, ini, fim, filters=None):
    """% da base (não bloqueada, com alguma compra) sem comprar há mais de 90 dias."""
    qs = Customer.objects.filter(tenant=tenant, blocked=False, last_purchase_at__isnull=False)
    n = qs.count()
    return _pct(qs.filter(last_purchase_at__lt=fim - timedelta(days=90)).count(), n) if n else None


def clientes_cadastrados(tenant, ini, fim, filters=None):
    return D(Customer.objects.filter(tenant=tenant, registered_at__range=(ini, fim)).count())


def positivacao_pct_base(tenant, ini, fim, filters=None):
    """Clientes positivados no período sobre a base ativa (90 dias)."""
    return _pct(positivacao(tenant, ini, fim, filters), clientes_ativos(tenant, ini, fim, filters))


def recompra_pct(tenant, ini, fim, filters=None):
    """% dos clientes positivados no período que já haviam comprado antes dele."""
    pos = set(notas_do_periodo(tenant, ini, fim, filters).filter(customer__isnull=False).values_list("customer_id", flat=True))
    if not pos:
        return None
    novos = set(Customer.objects.filter(tenant=tenant, id__in=pos, first_purchase_at__range=(ini, fim)).values_list("id", flat=True))
    return _pct(len(pos - novos), len(pos))


# --- Pessoas ------------------------------------------------------------------

def admissoes(tenant, ini, fim, filters=None):
    return D(Employee.objects.filter(tenant=tenant, admission_date__range=(ini, fim)).filter(_branch_q(filters)).count())


def tempo_medio_casa_anos(tenant, ini, fim, filters=None):
    qs = Employee.objects.filter(tenant=tenant, admission_date__isnull=False).filter(
        Q(dismissal_date__isnull=True) | Q(dismissal_date__gt=fim)).filter(_branch_q(filters))
    n, soma = 0, 0
    for e in qs.only("admission_date"):
        n += 1
        soma += (fim - e.admission_date).days
    return (D(soma) / n / 365).quantize(D("0.1")) if n else None


def motoristas_ativos(tenant, ini, fim, filters=None):
    return D(Employee.objects.filter(tenant=tenant, is_driver=True, is_active=True).filter(_branch_q(filters)).count())


def faturamento_por_funcionario(tenant, ini, fim, filters=None):
    hc = headcount(tenant, ini, fim, filters)
    fat = faturamento(tenant, ini, fim, filters)
    return _money(fat / hc) if hc and fat is not None else None


def folha_estimada(tenant, ini, fim, filters=None):
    """Soma dos salários cadastrados dos funcionários ativos (PCEMPR.VLSALARIO)."""
    qs = Employee.objects.filter(tenant=tenant, salary__isnull=False).filter(
        Q(dismissal_date__isnull=True) | Q(dismissal_date__gt=fim)).filter(_branch_q(filters))
    v = _sum(qs, "salary")
    return _money(v) if v else None


# --- Catálogo ----------------------------------------------------------------

def _m(key, label, unit, polarity, aggregation, group, description, entities, fn, decimals=2):
    return Metric(key, label, unit, polarity, aggregation, description, entities, fn, group, decimals)


CATALOG = [
    # Vendas
    _m("faturamento", "Faturamento líquido", "R$", "maior_melhor", "soma", "Vendas",
       "Soma das notas de saída não canceladas, fora bonificação/transferência/entrega futura (regra oficial do WinThor).",
       ["sales_invoice"], faturamento),
    _m("qtd_notas", "Notas emitidas", "un", "maior_melhor", "soma", "Vendas",
       "Quantidade de notas fiscais de venda no período.", ["sales_invoice"], qtd_notas, 0),
    _m("ticket_medio", "Ticket médio", "R$", "maior_melhor", "media", "Vendas",
       "Faturamento dividido pelo número de notas.", ["sales_invoice"], ticket_medio),
    _m("positivacao", "Clientes positivados", "un", "maior_melhor", "ultimo", "Vendas",
       "Clientes distintos que compraram no mês.", ["sales_invoice"], positivacao, 0),
    _m("clientes_ativos", "Clientes ativos (90 dias)", "un", "maior_melhor", "ultimo", "Vendas",
       "Clientes com compra nos últimos 90 dias.", ["customer"], clientes_ativos, 0),
    _m("novos_clientes", "Novos clientes", "un", "maior_melhor", "soma", "Vendas",
       "Clientes cuja primeira compra aconteceu no mês.", ["customer"], novos_clientes, 0),
    _m("churn_clientes_pct", "Churn de clientes", "%", "menor_melhor", "media", "Vendas",
       "% dos clientes ativos no trimestre anterior que não compraram no trimestre corrente.",
       ["sales_invoice"], churn_clientes_pct),
    _m("mix_skus", "Mix de produtos vendidos", "un", "maior_melhor", "ultimo", "Vendas",
       "SKUs distintos com venda no mês.", ["sales_invoice_item"], mix_skus, 0),
    _m("desconto_medio_pct", "Desconto médio praticado", "%", "menor_melhor", "media", "Vendas",
       "Diferença entre preço de tabela e preço praticado nos itens vendidos.", ["sales_invoice_item"], desconto_medio_pct),
    _m("bonificacao_pct", "Bonificação sobre faturamento", "%", "menor_melhor", "media", "Vendas",
       "Valor bonificado (CONDVENDA 5/6/11/12) sobre o faturamento.", ["sales_invoice"], bonificacao_pct),
    _m("devolucoes_pct", "Devoluções sobre vendas", "%", "menor_melhor", "media", "Vendas",
       "Valor devolvido (operações E1/ED/EL) sobre o valor vendido nos itens.", ["sales_invoice_item"], devolucoes_pct),
    _m("carteira_pedidos", "Carteira de pedidos", "R$", "maior_melhor", "ultimo", "Vendas",
       "Valor dos pedidos pendentes de faturamento.", ["order"], carteira_pedidos),
    _m("conversao_pedido_nota_pct", "Conversão pedido → nota", "%", "maior_melhor", "media", "Vendas",
       "% dos pedidos do mês que foram faturados.", ["order"], conversao_pedido_nota_pct),
    _m("corte_pct", "Pedidos com corte", "%", "menor_melhor", "media", "Logística",
       "% de pedidos em que algum item foi entregue a menos (QTFALTA).", ["order"], corte_pct),
    # Margem / DRE
    _m("margem_bruta_pct", "Margem bruta", "%", "maior_melhor", "media", "Financeiro",
       "(Venda − custo financeiro) / venda, nos itens faturados.", ["sales_invoice_item"], margem_bruta_pct),
    _m("cmv", "CMV", "R$", "menor_melhor", "soma", "Financeiro",
       "Custo da mercadoria vendida (custo financeiro × quantidade).", ["sales_invoice_item"], cmv),
    _m("despesas_competencia", "Despesas (competência)", "R$", "menor_melhor", "soma", "Financeiro",
       "Contas a pagar por competência, pagas ou não.", ["title_payable"], despesas_competencia),
    _m("folha_pct_faturamento", "Folha sobre faturamento", "%", "menor_melhor", "media", "Financeiro",
       "Salários (TIPOSERVICO 30) sobre o faturamento do mês.", ["title_payable", "sales_invoice"], folha_pct_faturamento),
    # Caixa e recebíveis
    _m("recebido", "Recebimentos", "R$", "maior_melhor", "soma", "Financeiro",
       "Títulos a receber baixados no mês.", ["title_receivable"], recebido),
    _m("despesas_pagas", "Pagamentos", "R$", "menor_melhor", "soma", "Financeiro",
       "Títulos a pagar baixados no mês.", ["title_payable"], despesas_pagas),
    _m("geracao_caixa", "Geração de caixa", "R$", "maior_melhor", "soma", "Financeiro",
       "Entradas menos saídas do extrato bancário.", ["cash_movement"], geracao_caixa),
    _m("saldo_caixa", "Saldo de caixa e bancos", "R$", "maior_melhor", "ultimo", "Financeiro",
       "Caixa + bancos + aplicações na última fotografia do financeiro.", ["financial_snapshot", "bank_account"], saldo_caixa),
    _m("a_receber_aberto", "Contas a receber em aberto", "R$", "menor_melhor", "ultimo", "Financeiro",
       "Títulos a receber ainda não baixados.", ["title_receivable"], a_receber_aberto),
    _m("a_receber_vencido", "A receber vencido", "R$", "menor_melhor", "ultimo", "Financeiro",
       "Títulos a receber vencidos e não pagos.", ["title_receivable"], a_receber_vencido),
    _m("inadimplencia_pct", "Inadimplência (+30 dias)", "%", "menor_melhor", "ultimo", "Financeiro",
       "Vencido há mais de 30 dias sobre o total em aberto.", ["title_receivable"], inadimplencia_pct),
    _m("prazo_medio_recebimento", "Prazo médio de recebimento", "dias", "menor_melhor", "media", "Financeiro",
       "Dias entre emissão e pagamento, ponderado pelo valor.", ["title_receivable"], prazo_medio_recebimento, 1),
    _m("a_pagar_aberto", "Contas a pagar em aberto", "R$", "menor_melhor", "ultimo", "Financeiro",
       "Títulos a pagar ainda não baixados.", ["title_payable"], a_pagar_aberto),
    _m("a_pagar_vencido", "A pagar vencido", "R$", "menor_melhor", "ultimo", "Financeiro",
       "Títulos a pagar vencidos e não pagos.", ["title_payable"], a_pagar_vencido),
    # Estoque e compras
    _m("estoque_valor", "Estoque a custo", "R$", "menor_melhor", "ultimo", "Estoque",
       "Saldo × custo médio dos produtos ativos.", ["stock"], estoque_valor),
    _m("cobertura_estoque_dias", "Cobertura de estoque", "dias", "menor_melhor", "ultimo", "Estoque",
       "Dias de venda cobertos pelo saldo disponível (giro diário do ERP), ponderado por custo.", ["stock"], cobertura_estoque_dias, 1),
    _m("ruptura_pct", "Ruptura", "%", "menor_melhor", "ultimo", "Estoque",
       "% dos itens com giro que estão zerados (disponível ≤ 0).", ["stock"], ruptura_pct),
    _m("giro_estoque", "Giro de estoque", "x", "maior_melhor", "media", "Estoque",
       "CMV do mês sobre o estoque a custo.", ["sales_invoice_item", "stock"], giro_estoque),
    _m("venda_perdida_qtd", "Venda perdida por falta", "un", "menor_melhor", "ultimo", "Estoque",
       "Unidades registradas pelo ERP como perdidas por ruptura.", ["stock"], venda_perdida_qtd, 1),
    _m("compras_valor", "Compras (entradas)", "R$", "menor_melhor", "soma", "Estoque",
       "Notas de entrada de fornecedores no mês.", ["purchase"], compras_valor),
    # Logística
    _m("cargas_expedidas", "Cargas expedidas", "un", "maior_melhor", "soma", "Logística",
       "Carregamentos que saíram no mês.", ["load"], cargas_expedidas, 0),
    _m("notas_por_carga", "Notas por carga", "un", "maior_melhor", "media", "Logística",
       "Média de notas por carregamento (densidade de entrega).", ["load"], notas_por_carga, 1),
    _m("peso_entregue_ton", "Peso entregue", "t", "maior_melhor", "soma", "Logística",
       "Toneladas expedidas no mês.", ["load"], peso_entregue_ton),
    _m("frete_pct_faturamento", "Frete sobre faturamento", "%", "menor_melhor", "media", "Logística",
       "Custo de frete das cargas sobre o faturamento.", ["load", "sales_invoice"], frete_pct_faturamento),
    # Pessoas
    _m("headcount", "Headcount", "un", "maior_melhor", "ultimo", "Pessoas",
       "Funcionários ativos no fim do mês.", ["employee"], headcount, 0),
    _m("turnover_pct", "Turnover", "%", "menor_melhor", "media", "Pessoas",
       "(Admissões + demissões) / 2 sobre o headcount.", ["employee"], turnover_pct),
    _m("desligamentos", "Desligamentos", "un", "menor_melhor", "soma", "Pessoas",
       "Demissões no mês.", ["employee"], desligamentos, 0),
    # Vendas (pedidos, RCAs, concentração, crescimento)
    _m("qtd_pedidos", "Pedidos digitados", "un", "maior_melhor", "soma", "Vendas",
       "Pedidos de venda do período não cancelados (PCPEDC).", ["order"], qtd_pedidos, 0),
    _m("pedido_medio", "Pedido médio", "R$", "maior_melhor", "media", "Vendas",
       "Valor médio dos pedidos digitados.", ["order"], pedido_medio),
    _m("pedidos_cancelados_pct", "Pedidos cancelados", "%", "menor_melhor", "media", "Vendas",
       "% dos pedidos do período cancelados (POSICAO C).", ["order"], pedidos_cancelados_pct),
    _m("rcas_ativos", "RCAs com venda", "un", "maior_melhor", "ultimo", "Vendas",
       "Vendedores com ao menos uma nota faturada no mês.", ["sales_invoice"], rcas_ativos, 0),
    _m("venda_media_por_rca", "Venda média por RCA", "R$", "maior_melhor", "media", "Vendas",
       "Faturamento dividido pelos RCAs com venda.", ["sales_invoice"], venda_media_por_rca),
    _m("clientes_por_rca", "Clientes positivados por RCA", "un", "maior_melhor", "media", "Vendas",
       "Positivação média por vendedor.", ["sales_invoice"], clientes_por_rca, 1),
    _m("notas_por_cliente", "Frequência de compra", "un", "maior_melhor", "media", "Vendas",
       "Notas por cliente positivado no mês.", ["sales_invoice"], notas_por_cliente),
    _m("itens_por_nota", "Itens por nota", "un", "maior_melhor", "media", "Vendas",
       "Média de itens (PCMOV) por nota faturada.", ["sales_invoice_item", "sales_invoice"], itens_por_nota, 1),
    _m("concentracao_top10_clientes_pct", "Concentração nos 10 maiores clientes", "%", "menor_melhor", "media", "Vendas",
       "Fatia do faturamento nos 10 maiores clientes.", ["sales_invoice"], concentracao_top10_clientes_pct),
    _m("concentracao_top_rca_pct", "Dependência do maior RCA", "%", "menor_melhor", "media", "Vendas",
       "Fatia do faturamento do vendedor que mais vende.", ["sales_invoice"], concentracao_top_rca_pct),
    _m("crescimento_faturamento_yoy_pct", "Crescimento do faturamento (ano a ano)", "%", "maior_melhor", "media", "Vendas",
       "Faturamento contra o mesmo período do ano anterior.", ["sales_invoice"], crescimento_faturamento_yoy_pct),
    _m("venda_perdida_corte", "Quantidade cortada nos pedidos", "un", "menor_melhor", "soma", "Vendas",
       "Itens cortados (QTFALTA) nos pedidos do período.", ["order"], venda_perdida_corte, 1),
    _m("pedidos_faturados_no_dia_pct", "Pedidos faturados no mesmo dia", "%", "maior_melhor", "media", "Logística",
       "% dos pedidos faturados no dia em que foram digitados.", ["order"], pedidos_faturados_no_dia_pct),
    _m("lucro_bruto", "Lucro bruto", "R$", "maior_melhor", "soma", "Financeiro",
       "Venda − custo financeiro dos itens faturados.", ["sales_invoice_item"], lucro_bruto),
    _m("markup_pct", "Markup", "%", "maior_melhor", "media", "Financeiro",
       "(Venda − custo) / custo nos itens faturados.", ["sales_invoice_item"], markup_pct),
    _m("preco_medio_item", "Preço médio por unidade", "R$", "maior_melhor", "media", "Vendas",
       "Valor vendido ÷ quantidade nos itens faturados.", ["sales_invoice_item"], preco_medio_item),
    # Financeiro (aging, prazos, liquidez, resultado)
    _m("a_receber_vencido_60_pct", "Carteira vencida há +60 dias", "%", "menor_melhor", "ultimo", "Financeiro",
       "Vencido há mais de 60 dias sobre o total em aberto.", ["title_receivable"], a_receber_vencido_60_pct),
    _m("titulos_pagos_no_prazo_pct", "Títulos pagos no prazo", "%", "maior_melhor", "media", "Financeiro",
       "% dos títulos baixados no mês pagos até o vencimento.", ["title_receivable"], titulos_pagos_no_prazo_pct),
    _m("atraso_medio_recebimento_dias", "Atraso médio dos recebimentos", "dias", "menor_melhor", "media", "Financeiro",
       "Dias além do vencimento nos títulos pagos com atraso, ponderado por valor.", ["title_receivable"], atraso_medio_recebimento_dias, 1),
    _m("multa_juros_recebidos", "Multa e juros recebidos", "R$", "maior_melhor", "soma", "Financeiro",
       "VALORMULTA dos títulos baixados no mês.", ["title_receivable"], multa_juros_recebidos),
    _m("prazo_medio_pagamento", "Prazo médio de pagamento", "dias", "maior_melhor", "media", "Financeiro",
       "Dias entre emissão e pagamento das contas a pagar baixadas.", ["title_payable"], prazo_medio_pagamento, 1),
    _m("a_pagar_vencido_pct", "Contas a pagar vencidas", "%", "menor_melhor", "ultimo", "Financeiro",
       "Vencido sobre o total a pagar em aberto.", ["title_payable"], a_pagar_vencido_pct),
    _m("a_pagar_proximos_30_dias", "A pagar nos próximos 30 dias", "R$", "menor_melhor", "ultimo", "Financeiro",
       "Títulos a pagar vencendo nos 30 dias seguintes.", ["title_payable"], a_pagar_proximos_30_dias),
    _m("a_receber_proximos_30_dias", "A receber nos próximos 30 dias", "R$", "maior_melhor", "ultimo", "Financeiro",
       "Títulos a receber vencendo nos 30 dias seguintes.", ["title_receivable"], a_receber_proximos_30_dias),
    _m("liquidez_cr_cp", "Liquidez (CR ÷ CP)", "x", "maior_melhor", "ultimo", "Financeiro",
       "Contas a receber em aberto sobre contas a pagar em aberto.", ["title_receivable", "title_payable"], liquidez_cr_cp),
    _m("dso_dias", "DSO (dias de venda em aberto)", "dias", "menor_melhor", "ultimo", "Financeiro",
       "A receber em aberto ÷ faturamento dos últimos 90 dias × 90.", ["title_receivable", "sales_invoice"], dso_dias, 1),
    _m("despesas_pct_faturamento", "Despesas sobre faturamento", "%", "menor_melhor", "media", "Financeiro",
       "Contas a pagar por competência sobre o faturamento.", ["title_payable", "sales_invoice"], despesas_pct_faturamento),
    _m("resultado_operacional", "Resultado operacional (aprox.)", "R$", "maior_melhor", "soma", "Financeiro",
       "Lucro bruto dos itens − despesas por competência.", ["sales_invoice_item", "title_payable"], resultado_operacional),
    _m("resultado_operacional_pct", "Margem operacional (aprox.)", "%", "maior_melhor", "media", "Financeiro",
       "Resultado operacional sobre o faturamento.", ["sales_invoice_item", "title_payable", "sales_invoice"], resultado_operacional_pct),
    _m("entradas_caixa", "Entradas de caixa", "R$", "maior_melhor", "soma", "Financeiro",
       "Créditos no extrato bancário (PCMOVCR tipo D).", ["cash_movement"], entradas_caixa),
    _m("saidas_caixa", "Saídas de caixa", "R$", "menor_melhor", "soma", "Financeiro",
       "Débitos no extrato bancário (PCMOVCR tipo C).", ["cash_movement"], saidas_caixa),
    _m("posicao_liquida_financeira", "Posição líquida (SALDOREAL)", "R$", "maior_melhor", "ultimo", "Financeiro",
       "Caixa + bancos + a receber − a pagar na última fotografia do financeiro.", ["financial_snapshot"], posicao_liquida_financeira),
    _m("estoque_financeiro_foto", "Estoque financeiro (PCFINANC)", "R$", "menor_melhor", "ultimo", "Estoque",
       "Valor do estoque na fotografia diária do financeiro.", ["financial_snapshot"], estoque_financeiro_foto),
    # Estoque
    _m("capital_parado", "Capital parado", "R$", "menor_melhor", "ultimo", "Estoque",
       "Estoque a custo dos itens sem venda no mês.", ["stock"], capital_parado),
    _m("capital_parado_pct", "Capital parado sobre o estoque", "%", "menor_melhor", "ultimo", "Estoque",
       "Itens sem giro no mês sobre o estoque total a custo.", ["stock"], capital_parado_pct),
    _m("itens_sem_giro_pct", "Itens sem giro", "%", "menor_melhor", "ultimo", "Estoque",
       "% dos itens com saldo que não venderam no mês.", ["stock"], itens_sem_giro_pct),
    _m("excesso_estoque", "Excesso sobre o estoque máximo", "R$", "menor_melhor", "ultimo", "Estoque",
       "Valor a custo acima do ESTMAX por produto × filial.", ["stock"], excesso_estoque),
    _m("abaixo_minimo_pct", "Itens abaixo do mínimo", "%", "menor_melhor", "ultimo", "Estoque",
       "% dos itens com estoque mínimo definido que estão abaixo dele.", ["stock"], abaixo_minimo_pct),
    _m("skus_com_estoque", "SKUs com estoque", "un", "maior_melhor", "ultimo", "Estoque",
       "Produtos ativos com saldo positivo.", ["stock"], skus_com_estoque, 0),
    _m("estoque_bloqueado", "Estoque bloqueado", "R$", "menor_melhor", "ultimo", "Estoque",
       "Quantidade bloqueada (avaria/quarentena) a custo.", ["stock"], estoque_bloqueado),
    # Compras
    _m("qtd_notas_entrada", "Notas de entrada", "un", "maior_melhor", "soma", "Compras",
       "Notas fiscais de compra recebidas no mês.", ["purchase"], qtd_notas_entrada, 0),
    _m("fornecedores_ativos", "Fornecedores com compra", "un", "maior_melhor", "ultimo", "Compras",
       "Fornecedores distintos com nota de entrada no mês.", ["purchase"], fornecedores_ativos, 0),
    _m("compra_media_por_nota", "Compra média por nota", "R$", "maior_melhor", "media", "Compras",
       "Valor médio das notas de entrada.", ["purchase"], compra_media_por_nota),
    _m("compras_pct_faturamento", "Compras sobre faturamento", "%", "menor_melhor", "media", "Compras",
       "Entradas de fornecedores sobre o faturamento do mês.", ["purchase", "sales_invoice"], compras_pct_faturamento),
    _m("concentracao_top5_fornecedores_pct", "Concentração nos 5 maiores fornecedores", "%", "menor_melhor", "media", "Compras",
       "Fatia das compras nos 5 maiores fornecedores.", ["purchase"], concentracao_top5_fornecedores_pct),
    _m("frete_compras_pct", "Frete sobre compras", "%", "menor_melhor", "media", "Compras",
       "Frete das notas de entrada sobre o valor comprado.", ["purchase"], frete_compras_pct),
    # Logística
    _m("valor_medio_por_carga", "Valor médio por carga", "R$", "maior_melhor", "media", "Logística",
       "Valor entregue por carregamento.", ["load"], valor_medio_por_carga),
    _m("peso_medio_por_carga_kg", "Peso médio por carga", "kg", "maior_melhor", "media", "Logística",
       "Quilos por carregamento (ocupação do veículo).", ["load"], peso_medio_por_carga_kg, 1),
    _m("tempo_medio_rota_dias", "Tempo médio em rota", "dias", "menor_melhor", "media", "Logística",
       "Dias entre saída e retorno das cargas.", ["load"], tempo_medio_rota_dias, 1),
    _m("cargas_em_rota", "Cargas em rota", "un", "menor_melhor", "ultimo", "Logística",
       "Cargas que saíram e ainda não retornaram.", ["load"], cargas_em_rota, 0),
    _m("cargas_canceladas_pct", "Cargas canceladas", "%", "menor_melhor", "media", "Logística",
       "% dos carregamentos cancelados.", ["load"], cargas_canceladas_pct),
    _m("custo_frete_por_kg", "Frete por kg", "R$", "menor_melhor", "media", "Logística",
       "Custo de frete por quilo entregue.", ["load"], custo_frete_por_kg, 4),
    _m("custo_frete_por_nota", "Frete por nota entregue", "R$", "menor_melhor", "media", "Logística",
       "Custo de frete por nota fiscal transportada.", ["load"], custo_frete_por_nota),
    # Fiscal
    _m("nfe_autorizadas_pct", "NF-e autorizadas", "%", "maior_melhor", "media", "Fiscal",
       "% das notas com SITUACAONFE = 100 (autorizada na SEFAZ).", ["sales_invoice"], nfe_autorizadas_pct),
    _m("notas_canceladas_pct", "Notas canceladas", "%", "menor_melhor", "media", "Fiscal",
       "% das notas de saída canceladas (DTCANCEL).", ["sales_invoice"], notas_canceladas_pct),
    _m("icms_pct_faturamento", "ICMS sobre faturamento", "%", "menor_melhor", "media", "Fiscal",
       "VLICMS das notas faturadas sobre o total.", ["sales_invoice"], icms_pct_faturamento),
    _m("st_pct_faturamento", "ICMS-ST sobre faturamento", "%", "menor_melhor", "media", "Fiscal",
       "Substituição tributária sobre o faturamento.", ["sales_invoice"], st_pct_faturamento),
    _m("ipi_pct_faturamento", "IPI sobre faturamento", "%", "menor_melhor", "media", "Fiscal",
       "IPI das notas faturadas sobre o total.", ["sales_invoice"], ipi_pct_faturamento),
    _m("carga_tributaria_pct", "Carga tributária na saída", "%", "menor_melhor", "media", "Fiscal",
       "ICMS + ST + IPI sobre o faturamento.", ["sales_invoice"], carga_tributaria_pct),
    _m("notas_por_dia_util", "Notas por dia útil", "un", "maior_melhor", "media", "Fiscal",
       "Notas faturadas por dia útil do período.", ["sales_invoice"], notas_por_dia_util, 1),
    # Clientes
    _m("base_clientes", "Base de clientes", "un", "maior_melhor", "ultimo", "Clientes",
       "Clientes cadastrados e não bloqueados.", ["customer"], base_clientes, 0),
    _m("clientes_bloqueados_pct", "Clientes bloqueados", "%", "menor_melhor", "ultimo", "Clientes",
       "% da base com BLOQUEIO = S ou excluída.", ["customer"], clientes_bloqueados_pct),
    _m("clientes_inativos_90_pct", "Clientes inativos (+90 dias)", "%", "menor_melhor", "ultimo", "Clientes",
       "% da base sem compra há mais de 90 dias.", ["customer"], clientes_inativos_90_pct),
    _m("clientes_cadastrados", "Clientes cadastrados no mês", "un", "maior_melhor", "soma", "Clientes",
       "Novos cadastros (DTCADASTRO) no período.", ["customer"], clientes_cadastrados, 0),
    _m("positivacao_pct_base", "Cobertura da base", "%", "maior_melhor", "media", "Clientes",
       "Clientes positivados sobre a base ativa de 90 dias.", ["sales_invoice", "customer"], positivacao_pct_base),
    _m("recompra_pct", "Recompra", "%", "maior_melhor", "media", "Clientes",
       "% dos positivados que já eram clientes antes do período.", ["sales_invoice", "customer"], recompra_pct),
    # Pessoas
    _m("admissoes", "Admissões", "un", "maior_melhor", "soma", "Pessoas",
       "Contratações no mês (PCEMPR.ADMISSAO).", ["employee"], admissoes, 0),
    _m("tempo_medio_casa_anos", "Tempo médio de casa", "anos", "maior_melhor", "ultimo", "Pessoas",
       "Média de anos desde a admissão dos ativos.", ["employee"], tempo_medio_casa_anos, 1),
    _m("motoristas_ativos", "Motoristas ativos", "un", "maior_melhor", "ultimo", "Pessoas",
       "Funcionários com TIPOMOTORISTA ativos.", ["employee"], motoristas_ativos, 0),
    _m("faturamento_por_funcionario", "Faturamento por funcionário", "R$", "maior_melhor", "media", "Pessoas",
       "Faturamento do mês dividido pelo headcount.", ["sales_invoice", "employee"], faturamento_por_funcionario),
]

METRICS = {m.key: m for m in CATALOG}


def get_metric(key) -> Optional[Metric]:
    return METRICS.get(key or "")


def month_bounds(period: date):
    ini = period.replace(day=1)
    nxt = (ini.replace(day=28) + timedelta(days=4)).replace(day=1)
    return ini, nxt - timedelta(days=1)


def compute_metric(key, tenant, period: date, filters=None):
    metric = get_metric(key)
    if metric is None:
        return None
    ini, fim = month_bounds(period)
    hoje = date.today()
    # Mês corrente: mede até hoje, não até o fim do mês.
    if fim > hoje:
        fim = hoje
    if ini > hoje:
        return None
    return metric.compute(tenant, ini, fim, filters or {})


def catalog_payload():
    return [
        {
            "key": m.key, "label": m.label, "unit": m.unit, "polarity": m.polarity,
            "aggregation": m.aggregation, "group": m.group, "description": m.description,
            "entities": m.entities, "decimals": m.decimals,
        }
        for m in CATALOG
    ]
