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
    CardSettlement,
    CashMovement,
    CreditAuthorization,
    Customer,
    CustomerCredit,
    DeliveryLoad,
    Employee,
    FinancialSnapshot,
    FinancialTitle,
    FvOrder,
    Mdfe,
    Order,
    OrderBlock,
    PosDaily,
    Product,
    PurchaseInvoice,
    PurchaseOrder,
    SalesInvoice,
    SalesInvoiceItem,
    SalesRep,
    StockBalance,
    SupplierCredit,
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


def _rep_q(filters, path="sales_rep"):
    """`sales_rep` aceita um código de RCA ("120") ou vários ("120,121") — visão por vendedor.

    `path=""` aplica o filtro no próprio SalesRep (campo `code`)."""
    code = (filters or {}).get("sales_rep")
    if not code:
        return Q()
    if isinstance(code, str):
        code = [c.strip() for c in code.split(",") if c.strip()]
    codes = [str(c) for c in code]
    if not codes:
        return Q()
    campo = f"{path}__code" if path else "code"
    if len(codes) == 1:
        return Q(**{campo: codes[0]})
    return Q(**{f"{campo}__in": codes})


def _sum(qs, expr):
    v = qs.aggregate(v=Sum(expr))["v"]
    return D(v) if v is not None else None


def _ate(fim):
    """Data de corte "como estava em": nunca no futuro. O mês corrente é medido até hoje."""
    hoje = date.today()
    return fim if fim < hoje else hoje


def _periodo_corrente(fim):
    """Período que inclui o presente. Métricas de fotografia (saldo do espelho hoje)
    só valem aqui — para um mês passado não existe "estoque de março" no espelho."""
    return fim >= date.today().replace(day=1)


def fotografia(fn):
    """Marca uma métrica de fotografia: fora do período corrente devolve None em vez
    de repetir o saldo de hoje em todos os meses do gráfico."""
    import functools

    @functools.wraps(fn)
    def wrapper(tenant, ini, fim, filters=None):
        if not _periodo_corrente(fim):
            return None
        return fn(tenant, ini, fim, filters)

    wrapper.fotografia = True
    return wrapper


def _aberto_em(qs, fim):
    """Títulos em aberto COMO ESTAVAM na data `fim`: emitidos até lá e ainda não pagos nela.
    Usar o status atual em mês passado esconde tudo que foi pago depois (a carteira
    vencida de janeiro parecia 20× menor que a de agosto só porque janeiro já foi cobrado)."""
    corte = _ate(fim)
    return (qs.exclude(status="canceled")
            .filter(Q(issue_date__isnull=True) | Q(issue_date__lte=corte))
            .filter(Q(paid_at__isnull=True) | Q(paid_at__gt=corte)))


def _sem_consolidada(qs):
    """Tira a filial virtual "TODAS FILIAIS" (99 no WinThor): é soma, não caixa real."""
    return qs.exclude(branch__name__icontains="TODAS FILIAIS").exclude(branch__code="99")


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
    ).filter(regras.filtro_notas_faturadas()).filter(_branch_q(filters)).filter(_rep_q(filters))


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
    """Clientes distintos com nota faturada nos 90 dias até o fim do período.

    Pelas notas, não por PCCLIENT.DTULTCOMP: a data da última compra é um
    campo de hoje, e em mês passado contava só quem parou de comprar naquele mês.
    """
    corte = _ate(fim)
    qs = notas_do_periodo(tenant, corte - timedelta(days=90), corte, filters).filter(customer__isnull=False)
    return D(qs.values("customer_id").distinct().count())


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
    ).filter(_branch_q(filters)).filter(_rep_q(filters))


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


@fotografia
def carteira_pedidos(tenant, ini, fim, filters=None):
    """Valor em pedidos pendentes (não faturados nem cancelados) hoje."""
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
    return _money(_sum(_aberto_em(_receber(tenant, filters), fim), "amount") or ZERO)


def a_receber_vencido(tenant, ini, fim, filters=None):
    return _money(_sum(_aberto_em(_receber(tenant, filters), fim).filter(due_date__lt=_ate(fim)), "amount") or ZERO)


def clientes_com_titulo_vencido(tenant, ini, fim, filters=None):
    """Clientes com pelo menos um título em aberto vencido (F_PCPREST_VENCIDA_BLOQUEIO)."""
    return D(_aberto_em(_receber(tenant, filters), fim).filter(due_date__lt=_ate(fim), customer__isnull=False)
             .values("customer_id").distinct().count())


def clientes_com_titulo_vencido_pct(tenant, ini, fim, filters=None):
    ativos = clientes_ativos(tenant, ini, fim, filters)
    return _pct(clientes_com_titulo_vencido(tenant, ini, fim, filters), ativos)


def inadimplencia_pct(tenant, ini, fim, filters=None):
    """Vencido há mais de 30 dias sobre o total em aberto, como estava no fim do período."""
    qs = _aberto_em(_receber(tenant, filters), fim)
    aberto = _sum(qs, "amount")
    vencido = _sum(qs.filter(due_date__lt=_ate(fim) - timedelta(days=30)), "amount") or ZERO
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
    return _money(_sum(_aberto_em(_pagar(tenant, filters), fim), "amount") or ZERO)


def a_pagar_vencido(tenant, ini, fim, filters=None):
    return _money(_sum(_aberto_em(_pagar(tenant, filters), fim).filter(due_date__lt=_ate(fim)), "amount") or ZERO)


def despesas_pagas(tenant, ini, fim, filters=None):
    return _money(_sum(_pagar(tenant, filters).filter(status="paid", paid_at__range=(ini, fim)), "amount_paid") or ZERO)


def despesas_competencia(tenant, ini, fim, filters=None):
    """Despesas pela competência (DTCOMPETENCIA), pagas ou não — visão de DRE."""
    return _money(_sum(_pagar(tenant, filters).exclude(status="canceled").filter(accrual_date__range=(ini, fim)), "amount") or ZERO)


def folha_pct_faturamento(tenant, ini, fim, filters=None):
    """Salários sobre o faturamento: PCLANC com TIPOSERVICO 30 ou conta (PCCONTA) de salário."""
    qs = _pagar(tenant, filters).exclude(status="canceled").filter(accrual_date__range=(ini, fim))
    folha = _sum(qs.filter(Q(tax_type="30") | Q(account__icontains="salar") | Q(account__icontains="folha")), "amount")
    return _pct(folha, faturamento(tenant, ini, fim, filters))


def saldo_caixa(tenant, ini, fim, filters=None):
    """Caixa + bancos + aplicações na última fotografia do período (PCFINANC); fallback PCBANCO."""
    snaps = _sem_consolidada(FinancialSnapshot.objects.filter(tenant=tenant, date__lte=_ate(fim)).filter(_branch_q(filters)))
    ultimo = snaps.order_by("-date").values_list("date", flat=True).first()
    if ultimo:
        agg = snaps.filter(date=ultimo).aggregate(b=Sum("bank_balance"), c=Sum("cash_balance"), a=Sum("investments"))
        return _money(D(agg["b"] or 0) + D(agg["c"] or 0) + D(agg["a"] or 0))
    if not _periodo_corrente(fim):
        return None
    saldo = _sum(_sem_consolidada(BankAccount.objects.filter(tenant=tenant).filter(_branch_q(filters))), "balance")
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


@fotografia
def cobertura_estoque_dias(tenant, ini, fim, filters=None):
    """Dias de estoque: estoque a custo ÷ CMV médio diário dos últimos 90 dias.

    A ponderação por PCEST.QTGIRODIA item a item dava 18 mil dias: itens de giro
    quase zero dominam a média. A régua financeira (estoque ÷ CMV/dia) é a que a
    diretoria usa.
    """
    est = estoque_valor(tenant, ini, fim, filters)
    corte = _ate(fim)
    custo90 = cmv(tenant, corte - timedelta(days=89), corte, filters)
    if not est or not custo90:
        return None
    return (est / (custo90 / 90)).quantize(D("0.1"))


@fotografia
def giro_estoque(tenant, ini, fim, filters=None):
    """CMV do período / estoque atual a custo."""
    custo = cmv(tenant, ini, _ate(fim), filters)
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
    """Frete das cargas (PCCARREG.VLFRETE) sobre o faturamento; se o cliente não
    preenche o frete na carga, usa as contas de frete do contas a pagar (PCLANC)."""
    frete = _sum(_cargas(tenant, ini, fim, filters), "freight")
    if not frete:
        qs = _pagar(tenant, filters).exclude(status="canceled").filter(accrual_date__range=(ini, fim), account__icontains="frete")
        frete = _sum(qs, "amount")
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
    ).filter(_branch_q(filters)).filter(_rep_q(filters))


# --- Força de vendas: o que o app do vendedor (Ion/MaxSoluções) apura --------
# Regras copiadas do que esses sistemas executam no WinThor: venda transmitida
# (PCPEDC.VLATEND sem bonificação), venda bloqueada (POSICAO B), lucratividade
# = (venda − custo) ÷ venda, curva ABC por RANK/RATIO_TO_REPORT, crédito
# disponível = limite + crédito − títulos − pedidos − cheques.

def valor_pedidos(tenant, ini, fim, filters=None):
    """Venda transmitida: valor dos pedidos digitados no período (sem bonificação)."""
    qs = _pedidos(tenant, ini, fim, filters).exclude(sale_type__in=regras.CONDVENDA_BONIFICACAO)
    v = _sum(qs, "total")
    return _money(v) if v is not None else None


def pedidos_bloqueados_valor(tenant, ini, fim, filters=None):
    """Venda bloqueada: pedidos pendentes na posição B (bloqueio comercial/financeiro)."""
    qs = Order.objects.filter(tenant=tenant, status=Order.Status.PENDING, erp_position="B").filter(_branch_q(filters)).filter(_rep_q(filters))
    return _money(_sum(qs, "total") or ZERO)


def pedidos_bloqueados_pct(tenant, ini, fim, filters=None):
    qs = _pedidos(tenant, ini, fim, filters)
    n = qs.count()
    return _pct(qs.filter(erp_position="B").count(), n) if n else None


def comissao_valor(tenant, ini, fim, filters=None):
    """Comissão gerada nos itens faturados: PERCOM × valor do item (PCMOV)."""
    qs = _itens_venda(tenant, ini, fim, filters).filter(commission_pct__isnull=False)
    expr = ExpressionWrapper(F("quantity") * F("unit_price") * F("commission_pct") / 100, output_field=DecimalField(max_digits=18, decimal_places=4))
    return _money(_sum(qs, expr) or ZERO)


def comissao_pct(tenant, ini, fim, filters=None):
    return _pct(comissao_valor(tenant, ini, fim, filters), _sum(_itens_venda(tenant, ini, fim, filters), _VALOR))


def _curva_a_pct(valores):
    """% dos elementos que somam 80 % do total (curva A)."""
    total = sum(valores)
    if not total:
        return None
    acumulado, n = ZERO, 0
    for v in sorted(valores, reverse=True):
        acumulado += v
        n += 1
        if acumulado >= total * D("0.8"):
            break
    return _pct(n, len(valores))


def clientes_curva_a_pct(tenant, ini, fim, filters=None):
    """% dos clientes positivados que respondem por 80 % da venda (curva A)."""
    rows = notas_do_periodo(tenant, ini, fim, filters).filter(customer__isnull=False).values("customer").annotate(v=Sum("total"))
    return _curva_a_pct([D(r["v"] or 0) for r in rows])


def skus_curva_a_pct(tenant, ini, fim, filters=None):
    """% dos produtos vendidos que respondem por 80 % da venda (curva A)."""
    rows = _itens_venda(tenant, ini, fim, filters).values("product").annotate(v=Sum(_VALOR))
    return _curva_a_pct([D(r["v"] or 0) for r in rows])


def mix_por_cliente(tenant, ini, fim, filters=None):
    """Produtos distintos por cliente positivado (mix médio da cesta)."""
    rows = _itens_venda(tenant, ini, fim, filters).filter(customer__isnull=False).values("customer").annotate(n=Count("product", distinct=True))
    ns = [r["n"] for r in rows]
    return (D(sum(ns)) / len(ns)).quantize(D("0.1")) if ns else None


def _credito_por_cliente(tenant, fim, filters):
    """Limite − títulos em aberto − pedidos pendentes, cliente a cliente (aproximação da PKG_LIMITECREDITO)."""
    clientes = Customer.objects.filter(tenant=tenant, blocked=False, credit_limit__gt=0).filter(_rep_q(filters))
    abertos = dict(FinancialTitle.objects.filter(tenant=tenant, kind="receivable", status="open", customer__in=clientes)
                   .values_list("customer").annotate(v=Sum("amount")).values_list("customer", "v"))
    pendentes = dict(Order.objects.filter(tenant=tenant, status=Order.Status.PENDING, customer__in=clientes)
                     .exclude(sale_type__in=[8, 13]).values_list("customer").annotate(v=Sum("total")).values_list("customer", "v"))
    for c in clientes.only("id", "credit_limit"):
        yield c.id, D(c.credit_limit) - D(abertos.get(c.id) or 0) - D(pendentes.get(c.id) or 0)


def credito_disponivel_carteira(tenant, ini, fim, filters=None):
    """Soma do crédito disponível dos clientes com limite (sem cheques nem sazonal — aproximação)."""
    vals = [max(v, ZERO) for _, v in _credito_por_cliente(tenant, fim, filters)]
    return _money(sum(vals)) if vals else None


def clientes_sem_credito_pct(tenant, ini, fim, filters=None):
    """% dos clientes com limite cujo crédito disponível está zerado ou negativo."""
    vals = [v for _, v in _credito_por_cliente(tenant, fim, filters)]
    return _pct(sum(1 for v in vals if v <= 0), len(vals)) if vals else None


def clientes_positivados_delta(tenant, ini, fim, filters=None):
    """Positivados no período − positivados no período anterior de mesmo tamanho."""
    dias = (fim - ini).days + 1
    atual = positivacao(tenant, ini, fim, filters)
    anterior = positivacao(tenant, ini - timedelta(days=dias), ini - timedelta(days=1), filters)
    return atual - anterior


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


# --- Peso e volume vendidos (varredura: SUM(QTCONT × PESOLIQ) aparece em 300+ objetos) --

_PESO = ExpressionWrapper(F("quantity") * F("product__net_weight"), output_field=DecimalField(max_digits=18, decimal_places=4))


def peso_vendido_ton(tenant, ini, fim, filters=None):
    """Toneladas vendidas: quantidade × peso líquido do produto (PCPRODUT.PESOLIQ)."""
    v = _sum(_itens_venda(tenant, ini, fim, filters).filter(product__net_weight__gt=0), _PESO)
    return (D(v) / 1000).quantize(D("0.01")) if v is not None else None


def preco_medio_kg(tenant, ini, fim, filters=None):
    qs = _itens_venda(tenant, ini, fim, filters).filter(product__net_weight__gt=0)
    agg = qs.aggregate(v=Sum(_VALOR), p=Sum(_PESO))
    return _money(D(agg["v"]) / D(agg["p"])) if agg["p"] else None


def custo_medio_kg(tenant, ini, fim, filters=None):
    qs = _itens_venda(tenant, ini, fim, filters).filter(product__net_weight__gt=0, cost__isnull=False)
    agg = qs.aggregate(c=Sum(_CUSTO), p=Sum(_PESO))
    return _money(D(agg["c"]) / D(agg["p"])) if agg["p"] else None


# --- Financeiro: aging, prazos, liquidez --------------------------------------

def a_receber_vencido_60_pct(tenant, ini, fim, filters=None):
    """Vencido há mais de 60 dias sobre o total em aberto (carteira envelhecida), como estava no fim do período."""
    qs = _aberto_em(_receber(tenant, filters), fim)
    aberto = _sum(qs, "amount")
    venc = _sum(qs.filter(due_date__lt=_ate(fim) - timedelta(days=60)), "amount") or ZERO
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
    corte = _ate(fim)
    return _money(_sum(_aberto_em(_receber(tenant, filters), fim).filter(due_date__range=(corte, corte + timedelta(days=30))), "amount") or ZERO)


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
    snaps = _sem_consolidada(FinancialSnapshot.objects.filter(tenant=tenant, date__lte=_ate(fim)).filter(_branch_q(filters)))
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


# --- Carteira por RCA: o que o BI/geomarketing (schema GEO, F_BI_CARTEIRA,
# F_BI_CLISEMVENDAMES, F_BI_RCASEMVENDA) apura, lido direto do espelho ------------

def clientes_perdidos_mes(tenant, ini, fim, filters=None):
    """Clientes positivados no mês anterior que não compraram neste (F_BI_CLISEMVENDAMES)."""
    ini_ant = (ini.replace(day=1) - timedelta(days=1)).replace(day=1)
    fim_ant = ini.replace(day=1) - timedelta(days=1)
    anteriores = set(notas_do_periodo(tenant, ini_ant, fim_ant, filters).filter(customer__isnull=False).values_list("customer_id", flat=True))
    atuais = set(notas_do_periodo(tenant, ini, fim, filters).filter(customer__isnull=False).values_list("customer_id", flat=True))
    return D(len(anteriores - atuais))


def rcas_sem_venda(tenant, ini, fim, filters=None):
    """Vendedores ativos sem nenhuma nota faturada no período (F_BI_RCASEMVENDA)."""
    ativos = set(SalesRep.objects.filter(tenant=tenant, is_active=True).filter(_rep_q(filters, path="")).values_list("id", flat=True))
    com_venda = set(notas_do_periodo(tenant, ini, fim, filters).filter(sales_rep__isnull=False).values_list("sales_rep_id", flat=True))
    return D(len(ativos - com_venda))


def carteira_positivada_pct(tenant, ini, fim, filters=None):
    """Positivados ÷ carteira (clientes não bloqueados com RCA) — a régua da F_BI_CARTEIRA."""
    carteira = Customer.objects.filter(tenant=tenant, blocked=False, sales_rep__isnull=False).filter(_rep_q(filters)).count()
    return _pct(positivacao(tenant, ini, fim, filters), carteira) if carteira else None


def carteira_inativa_pct(tenant, ini, fim, filters=None):
    """% da carteira sem compra há mais de NUMDIASCLIINATIV (90) dias — F_BI_CARTEIRA.INATIVO."""
    qs = Customer.objects.filter(tenant=tenant, blocked=False, sales_rep__isnull=False).filter(_rep_q(filters))
    n = qs.count()
    inativos = qs.filter(Q(last_purchase_at__lt=fim - timedelta(days=90)) | Q(last_purchase_at__isnull=True)).count()
    return _pct(inativos, n) if n else None


# --- WMS: ordens de serviço do armazém (PCMOVENDPEND agregada por OS) ---------

def _os(tenant, ini, fim, filters):
    from .models import WmsOrder

    return WmsOrder.objects.filter(tenant=tenant, date__range=(ini, fim), operation__startswith="S").exclude(
        position="C").filter(_branch_q(filters))


def wms_os_concluidas(tenant, ini, fim, filters=None):
    return D(_os(tenant, ini, fim, filters).filter(picking_end__isnull=False).count())


def _media_minutos(qs, campo_ini, campo_fim, peso="lines"):
    total, soma = ZERO, ZERO
    for o in qs.only(campo_ini, campo_fim, peso):
        a, b = getattr(o, campo_ini), getattr(o, campo_fim)
        if not a or not b or b < a:
            continue
        w = D(getattr(o, peso) or 1)
        total += w
        soma += w * D((b - a).total_seconds() / 60)
    return (soma / total).quantize(D("0.1")) if total else None


def wms_tempo_separacao_min(tenant, ini, fim, filters=None):
    return _media_minutos(_os(tenant, ini, fim, filters).filter(picking_start__isnull=False, picking_end__isnull=False), "picking_start", "picking_end")


def wms_tempo_conferencia_min(tenant, ini, fim, filters=None):
    return _media_minutos(_os(tenant, ini, fim, filters).filter(check_start__isnull=False, check_end__isnull=False), "check_start", "check_end")


def wms_os_pendentes(tenant, ini, fim, filters=None):
    from .models import WmsOrder

    return D(WmsOrder.objects.filter(tenant=tenant, date__lte=fim, operation__startswith="S", picking_end__isnull=True)
             .exclude(position="C").filter(_branch_q(filters)).count())


def wms_linhas_por_hora(tenant, ini, fim, filters=None):
    linhas, horas = ZERO, ZERO
    for o in _os(tenant, ini, fim, filters).filter(picking_start__isnull=False, picking_end__isnull=False).only("picking_start", "picking_end", "lines"):
        seg = (o.picking_end - o.picking_start).total_seconds()
        if seg <= 0:
            continue
        linhas += D(o.lines or 0)
        horas += D(seg / 3600)
    return (linhas / horas).quantize(D("0.1")) if horas else None


def wms_corte_pct(tenant, ini, fim, filters=None):
    qs = _os(tenant, ini, fim, filters)
    return _pct(_sum(qs, "qty_canceled") or ZERO, _sum(qs, "qty"))


def wms_erros_conferencia(tenant, ini, fim, filters=None):
    v = _sum(_os(tenant, ini, fim, filters), "errors")
    return D(v) if v is not None else None


# --- Entrega lida direto do WinThor (PCCARREG: NUMENT, NUMCID, KM) -------------
# O que o roteirizador mostra por carga o WinThor também guarda: clientes e
# praças distintas (rotina 1743) e o odômetro do acerto. Vale para qualquer
# cliente, com ou sem FusionTrak.

def entregas_por_carga(tenant, ini, fim, filters=None):
    qs = _cargas(tenant, ini, fim, filters).filter(num_customers__isnull=False)
    n = qs.count()
    v = _sum(qs, "num_customers")
    return (D(v) / n).quantize(D("0.1")) if n and v is not None else None


def cidades_por_carga_erp(tenant, ini, fim, filters=None):
    qs = _cargas(tenant, ini, fim, filters).filter(num_cities__isnull=False)
    n = qs.count()
    v = _sum(qs, "num_cities")
    return (D(v) / n).quantize(D("0.1")) if n and v is not None else None


def km_por_carga(tenant, ini, fim, filters=None):
    """KMFINAL − KMINICIAL do acerto, nas cargas com odômetro preenchido."""
    qs = _cargas(tenant, ini, fim, filters).filter(km_start__gt=0, km_end__gt=F("km_start"))
    n = qs.count()
    if not n:
        return None
    expr = ExpressionWrapper(F("km_end") - F("km_start"), output_field=DecimalField(max_digits=12, decimal_places=1))
    return (D(_sum(qs, expr)) / n).quantize(D("0.1"))


def km_por_entrega(tenant, ini, fim, filters=None):
    qs = _cargas(tenant, ini, fim, filters).filter(km_start__gt=0, km_end__gt=F("km_start"), num_invoices__gt=0)
    expr = ExpressionWrapper(F("km_end") - F("km_start"), output_field=DecimalField(max_digits=12, decimal_places=1))
    km, notas = _sum(qs, expr), _sum(qs, "num_invoices")
    return (D(km) / D(notas)).quantize(D("0.01")) if km is not None and notas else None


def cargas_sem_km_pct(tenant, ini, fim, filters=None):
    """% das cargas retornadas sem odômetro no acerto (dado que o roteirizador cobra)."""
    qs = _cargas(tenant, ini, fim, filters).filter(return_date__isnull=False)
    n = qs.count()
    return _pct(qs.filter(Q(km_end__isnull=True) | Q(km_end__lte=0)).count(), n) if n else None


# --- Roteirização (FusionTrak) --------------------------------------------------

def _rotas(tenant, ini, fim, filters):
    from .models import RouteLoad

    return RouteLoad.objects.filter(tenant=tenant, departure_date__range=(ini, fim)).filter(_branch_q(filters))


def cargas_roteirizadas_pct(tenant, ini, fim, filters=None):
    n = cargas_expedidas(tenant, ini, fim, filters)
    return _pct(_rotas(tenant, ini, fim, filters).filter(routed_at__isnull=False).count(), n) if n else None


def ocupacao_peso_pct(tenant, ini, fim, filters=None):
    qs = _rotas(tenant, ini, fim, filters).filter(max_weight__gt=0)
    return _pct(_sum(qs, "weight") or ZERO, _sum(qs, "max_weight"))


def entregas_por_carga_roteirizada(tenant, ini, fim, filters=None):
    qs = _rotas(tenant, ini, fim, filters)
    n = qs.count()
    v = _sum(qs, "num_customers")
    return (D(v) / n).quantize(D("0.1")) if n and v is not None else None


def cidades_por_carga(tenant, ini, fim, filters=None):
    qs = _rotas(tenant, ini, fim, filters)
    n = qs.count()
    v = _sum(qs, "num_cities")
    return (D(v) / n).quantize(D("0.1")) if n and v is not None else None


def ocorrencias_entrega(tenant, ini, fim, filters=None):
    from .models import DeliveryEvent

    return D(DeliveryEvent.objects.filter(tenant=tenant, occurred_at__range=(ini, fim)).exclude(reason_id__isnull=True).exclude(reason_id=0).count())


def entregas_com_ocorrencia_pct(tenant, ini, fim, filters=None):
    from .models import DeliveryEvent

    qs = DeliveryEvent.objects.filter(tenant=tenant, occurred_at__range=(ini, fim), order_number__gt="")
    n = qs.values("order_number").distinct().count()
    return _pct(qs.exclude(reason_id__isnull=True).exclude(reason_id=0).values("order_number").distinct().count(), n) if n else None


# --- Catálogo ----------------------------------------------------------------

# --- Varredura completa do WinThor: tabelas novas do espelho ---------------------
# "Visto na última carga": tabelas em que o ERP APAGA a linha (fila de bloqueio,
# caixa de entrada do FV) só contam o que o agente ainda enxergou há pouco.

_JANELA_VISTO = timedelta(hours=6)


def _visto_recente():
    from django.utils import timezone

    return timezone.now() - _JANELA_VISTO


def fila_bloqueio_valor(tenant, ini, fim, filters=None):
    """Valor (PCPEDC.VLTOTAL) dos pedidos com bloqueio STATUS = B ainda presente no ERP."""
    peds = OrderBlock.objects.filter(tenant=tenant, status="B", synced_at__gte=_visto_recente()) \
        .values_list("order_number", flat=True).distinct()
    qs = Order.objects.filter(tenant=tenant, number__in=list(peds)).filter(_branch_q(filters))
    return _money(_sum(qs, "total") or ZERO)


def tempo_fila_bloqueio_horas(tenant, ini, fim, filters=None):
    """Média de DTLIBERA − DTINCLUSAO dos bloqueios liberados no período."""
    pares = OrderBlock.objects.filter(
        tenant=tenant, released_at__date__range=(ini, fim), blocked_at__isnull=False,
    ).values_list("blocked_at", "released_at")
    horas = [(r - b).total_seconds() / 3600 for b, r in pares if r and b and r >= b]
    return D(sum(horas) / len(horas)).quantize(D("0.1")) if horas else None


def pedidos_fv_pendentes(tenant, ini, fim, filters=None):
    """Pedidos em PCPEDCFV ainda não importados (IMPORTADO = 0 e sem NUMPED)."""
    qs = FvOrder.objects.filter(
        tenant=tenant, imported=False, order_number="", synced_at__gte=_visto_recente(),
    ).filter(_branch_q(filters))
    return D(qs.count())


def rcas_flex_negativo(tenant, ini, fim, filters=None):
    """RCAs ativos com conta corrente (flex) negativa: PCUSUARI.VLCORRENTE < 0."""
    return D(SalesRep.objects.filter(tenant=tenant, is_active=True, flex_balance__lt=0).count())


def _creditos_abertos(tenant, fim, filters):
    return CustomerCredit.objects.filter(
        tenant=tenant, launched_at__lte=fim, used_at__isnull=True, canceled_at__isnull=True, reversed_at__isnull=True,
    ).filter(_branch_q(filters))


def creditos_cliente_aberto(tenant, ini, fim, filters=None):
    """PCCRECLI sem DTDESCONTO, DTCANCEL e DTESTORNO (fora cashback)."""
    return _money(_sum(_creditos_abertos(tenant, fim, filters).filter(is_cashback=False), "amount") or ZERO)


def cashback_a_expirar(tenant, ini, fim, filters=None):
    """Cashback em aberto com validade nos próximos 30 dias."""
    qs = _creditos_abertos(tenant, fim, filters).filter(
        is_cashback=True, cashback_expires_at__range=(fim, fim + timedelta(days=30)),
    )
    return _money(_sum(qs, "amount") or ZERO)


def credito_autorizado(tenant, ini, fim, filters=None):
    """Σ PCAUTORC.VLLIBERADO das autorizações do período."""
    qs = CreditAuthorization.objects.filter(tenant=tenant, date__range=(ini, fim))
    return _money(_sum(qs, "released_value") or ZERO)


def taxa_cartao_pct(tenant, ini, fim, filters=None):
    """(bruto − líquido) ÷ bruto das parcelas de cartão vendidas no período."""
    qs = CardSettlement.objects.filter(tenant=tenant, date__range=(ini, fim), net__isnull=False).filter(_branch_q(filters))
    agg = qs.aggregate(b=Sum("gross"), l=Sum("net"))
    if not agg["b"]:
        return None
    return _pct(D(agg["b"]) - D(agg["l"] or 0), agg["b"])


def _pdv(tenant, ini, fim, filters):
    return PosDaily.objects.filter(tenant=tenant, date__range=(ini, fim)).filter(_branch_q(filters))


def pdv_cupons(tenant, ini, fim, filters=None):
    return D(_sum(_pdv(tenant, ini, fim, filters), "coupons") or 0)


def pdv_ticket_medio(tenant, ini, fim, filters=None):
    agg = _pdv(tenant, ini, fim, filters).aggregate(v=Sum("gross_sales"), c=Sum("coupons"))
    return _money(D(agg["v"]) / D(agg["c"])) if agg["c"] and agg["v"] is not None else None


def titulos_prorrogados(tenant, ini, fim, filters=None):
    """Títulos cujo vencimento original (DTVENCANTERIOR) caiu no período e foi prorrogado."""
    return D(_receber(tenant, filters).filter(previous_due_date__range=(ini, fim)).exclude(status="canceled").count())


def desconto_na_baixa(tenant, ini, fim, filters=None):
    """Σ PCPREST.VALORDESC dos títulos pagos no período."""
    return _money(_sum(_receber(tenant, filters).filter(status="paid", paid_at__range=(ini, fim)), "discount_paid") or ZERO)


def pagar_sem_dupla_autorizacao(tenant, ini, fim, filters=None):
    """Títulos a pagar em aberto sem os dois autorizadores (CODFUNCAUTOR1 e 2)."""
    qs = _pagar(tenant, filters).filter(status="open").filter(Q(authorizer1="") | Q(authorizer2=""))
    return D(qs.count())


def adiantamentos_fornecedor_aberto(tenant, ini, fim, filters=None):
    """Adiantamentos (PCLANC.ADIANTAMENTO = S) pagos e ainda não abatidos em nota."""
    qs = _pagar(tenant, filters).filter(is_advance=True, status="paid")
    agg = qs.aggregate(a=Sum("amount"), u=Sum("advance_used"))
    total = D(agg["a"] or 0) - D(agg["u"] or 0)
    return _money(total if total > 0 else ZERO)


def itens_sem_inventario_pct(tenant, ini, fim, filters=None):
    """Itens com saldo sem contagem (DTULTINVENT) há mais de 90 dias."""
    qs = _estoque(tenant, filters).filter(quantity__gt=0)
    total = qs.count()
    sem = qs.filter(Q(last_inventory_at__isnull=True) | Q(last_inventory_at__lt=fim - timedelta(days=90))).count()
    return _pct(sem, total)


def pedidos_compra_atrasados(tenant, ini, fim, filters=None):
    """Pedidos de compra com DTPREVENT vencida e entrega incompleta (VLENTREGUE < 99% de VLTOTAL)."""
    qs = PurchaseOrder.objects.filter(
        tenant=tenant, expected_at__lt=fim, issue_date__gte=fim - timedelta(days=365), total__gt=0,
    ).filter(Q(delivered_value__isnull=True) | Q(delivered_value__lt=F("total") * D("0.99"))).filter(_branch_q(filters))
    return D(qs.count())


def verba_fornecedor_aberta(tenant, ini, fim, filters=None):
    """PCVERBA sem quitação nem cancelamento: VALOR − VPAGO."""
    qs = SupplierCredit.objects.filter(
        tenant=tenant, issue_date__lte=fim, settled_at__isnull=True, canceled_at__isnull=True,
    ).filter(_branch_q(filters))
    agg = qs.aggregate(a=Sum("amount"), p=Sum("paid"))
    return _money(D(agg["a"] or 0) - D(agg["p"] or 0))


def ciclo_carga_horas(tenant, ini, fim, filters=None):
    """Horas entre montagem (DATAMON) e conferência (DATACONF) das cargas expedidas no período."""
    pares = _cargas(tenant, ini, fim, filters).filter(
        assembled_at__isnull=False, checked_at__isnull=False,
    ).values_list("assembled_at", "checked_at")
    horas = [(c - a).total_seconds() / 3600 for a, c in pares if c >= a]
    return D(sum(horas) / len(horas)).quantize(D("0.1")) if horas else None


def cargas_alem_prazo_rota(tenant, ini, fim, filters=None):
    """Cargas retornadas em mais dias do que PCROTAEXP.PRAZOPREVENT da rota principal."""
    linhas = _cargas(tenant, ini, fim, filters).filter(
        return_date__isnull=False, route_lead_days__isnull=False,
    ).values_list("departure_date", "return_date", "route_lead_days")
    return D(sum(1 for s, r, p in linhas if (r - s).days > p))


def nfe_denegadas(tenant, ini, fim, filters=None):
    """PCNFSAID.SITUACAONFE em 110 (denegada), 205, 301, 302."""
    codigos = ["110", "205", "301", "302", "110.0", "205.0", "301.0", "302.0"]
    qs = SalesInvoice.objects.filter(tenant=tenant, issued_at__range=(ini, fim), nfe_status__in=codigos).filter(_branch_q(filters))
    return D(qs.count())


def mdfe_pendentes(tenant, ini, fim, filters=None):
    """MDF-e gerados sem protocolo de autorização e não cancelados."""
    qs = Mdfe.objects.filter(tenant=tenant, generated_at__date__lte=fim, protocol="", is_canceled=False).filter(_branch_q(filters))
    return D(qs.count())


def cnh_vencendo_30d(tenant, ini, fim, filters=None):
    """Motoristas ativos com CNH vencida ou vencendo em 30 dias."""
    qs = Employee.objects.filter(
        tenant=tenant, is_active=True, is_driver=True, cnh_expires_at__lte=fim + timedelta(days=30),
    ).filter(_branch_q(filters))
    return D(qs.count())


def usuarios_de_desligados(tenant, ini, fim, filters=None):
    """Funcionários com DTDEMISSAO e ainda com USUARIOBD (login do WinThor)."""
    qs = Employee.objects.filter(tenant=tenant, dismissal_date__isnull=False, dismissal_date__lte=fim, has_db_user=True)
    return D(qs.filter(_branch_q(filters)).count())


# Campo de data de cada fato: define desde quando o espelho cobre um mês inteiro.
_DATA_DO_FATO = {
    "sales_invoice": (SalesInvoice, "issued_at"), "sales_invoice_item": (SalesInvoiceItem, "moved_at"),
    "title_receivable": (FinancialTitle, "issue_date"), "title_payable": (FinancialTitle, "issue_date"),
    "order": (Order, "order_date"), "purchase": (PurchaseInvoice, "entry_date"),
    "load": (DeliveryLoad, "departure_date"), "cash_movement": (CashMovement, "moved_at"),
    "financial_snapshot": (FinancialSnapshot, "date"), "card_settlement": (CardSettlement, "date"),
    "pos_daily": (PosDaily, "date"), "purchase_order": (PurchaseOrder, "issue_date"),
    "supplier_credit": (SupplierCredit, "issue_date"), "customer_credit": (CustomerCredit, "launched_at"),
    "credit_auth": (CreditAuthorization, "date"),
}


def primeiro_mes_completo(tenant_id, entity):
    """Dia 1 do primeiro mês inteiramente coberto pelo fato no espelho (None = cadastro, sempre ok)."""
    from django.db.models import Min

    par = _DATA_DO_FATO.get(entity)
    if par is None:
        return None
    model, campo = par
    extra = {}
    if entity == "title_receivable":
        extra = {"kind": FinancialTitle.Kind.RECEIVABLE}
    elif entity == "title_payable":
        extra = {"kind": FinancialTitle.Kind.PAYABLE}
    inicio = model.objects.filter(tenant_id=tenant_id, **extra).aggregate(m=Min(campo))["m"]
    if inicio is None:
        return None
    if hasattr(inicio, "date"):
        inicio = inicio.date()
    if inicio.day == 1:
        return inicio
    return (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)


# Métricas de fotografia: leem o saldo de HOJE do espelho (estoque, cadastro,
# fila, pedidos pendentes). Em mês passado devolvem None — antes repetiam o
# número de hoje em todos os meses e o gráfico virava uma linha reta.
_FOTOGRAFIAS = (
    "estoque_valor", "ruptura_pct", "venda_perdida_qtd", "capital_parado", "capital_parado_pct",
    "itens_sem_giro_pct", "excesso_estoque", "abaixo_minimo_pct", "skus_com_estoque", "estoque_bloqueado",
    "itens_sem_inventario_pct", "clientes_inativos_90_pct", "clientes_bloqueados_pct", "base_clientes",
    "credito_disponivel_carteira", "clientes_sem_credito_pct", "fila_bloqueio_valor", "pedidos_fv_pendentes",
    "rcas_flex_negativo", "pagar_sem_dupla_autorizacao", "adiantamentos_fornecedor_aberto", "cargas_em_rota",
    "wms_os_pendentes",
)
for _nome in _FOTOGRAFIAS:
    if _nome in globals() and not getattr(globals()[_nome], "fotografia", False):
        globals()[_nome] = fotografia(globals()[_nome])


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
    _m("peso_vendido_ton", "Peso vendido", "t", "maior_melhor", "soma", "Vendas",
       "Quantidade × PESOLIQ do produto nos itens faturados, em toneladas.", ["sales_invoice_item", "product"], peso_vendido_ton),
    _m("preco_medio_kg", "Preço médio por kg", "R$", "maior_melhor", "media", "Vendas",
       "Valor vendido ÷ quilos vendidos.", ["sales_invoice_item", "product"], preco_medio_kg),
    _m("custo_medio_kg", "Custo médio por kg", "R$", "menor_melhor", "media", "Financeiro",
       "Custo dos itens vendidos ÷ quilos vendidos.", ["sales_invoice_item", "product"], custo_medio_kg),
    _m("clientes_com_titulo_vencido", "Clientes com título vencido", "clientes", "menor_melhor", "ultimo", "Financeiro",
       "Clientes distintos com título a receber em aberto vencido no fim do período.", ["financial_title"], clientes_com_titulo_vencido),
    _m("clientes_com_titulo_vencido_pct", "Clientes com título vencido (%)", "%", "menor_melhor", "ultimo", "Financeiro",
       "Clientes com título vencido ÷ clientes ativos.", ["financial_title", "customer"], clientes_com_titulo_vencido_pct),
    # Varredura completa do WinThor: tabelas novas do espelho
    _m("fila_bloqueio_valor", "Pedidos bloqueados aguardando liberação", "R$", "menor_melhor", "ultimo", "Vendas",
       "Valor dos pedidos com bloqueio STATUS = B ainda presente no ERP.", ["order_block", "order"], fila_bloqueio_valor),
    _m("tempo_fila_bloqueio_horas", "Tempo médio em fila de bloqueio", "h", "menor_melhor", "media", "Vendas",
       "Média de DTLIBERA − DTINCLUSAO dos bloqueios liberados no período.", ["order_block"], tempo_fila_bloqueio_horas, decimals=1),
    _m("pedidos_fv_pendentes", "Pedidos do força de vendas aguardando integração", "pedidos", "menor_melhor", "ultimo", "Vendas",
       "PCPEDCFV com IMPORTADO = 0 e sem NUMPED.", ["fv_order"], pedidos_fv_pendentes, decimals=0),
    _m("rcas_flex_negativo", "RCAs com flex negativo", "un", "menor_melhor", "ultimo", "Vendas",
       "RCAs ativos com PCUSUARI.VLCORRENTE < 0.", ["salesrep"], rcas_flex_negativo, decimals=0),
    _m("creditos_cliente_aberto", "Créditos de devolução em aberto", "R$", "menor_melhor", "ultimo", "Clientes",
       "PCCRECLI sem uso, cancelamento ou estorno (fora cashback).", ["customer_credit"], creditos_cliente_aberto),
    _m("cashback_a_expirar", "Cashback a expirar", "R$", "menor_melhor", "ultimo", "Clientes",
       "Cashback em aberto com validade nos próximos 30 dias.", ["customer_credit"], cashback_a_expirar),
    _m("credito_autorizado", "Crédito liberado por autorização", "R$", "menor_melhor", "soma", "Clientes",
       "Σ PCAUTORC.VLLIBERADO no período.", ["credit_auth"], credito_autorizado),
    _m("taxa_cartao_pct", "Custo de adquirência de cartão", "%", "menor_melhor", "media", "Financeiro",
       "(bruto − líquido) ÷ bruto das parcelas de cartão do período.", ["card_settlement"], taxa_cartao_pct),
    _m("pdv_cupons", "Cupons emitidos no PDV", "cupons", "maior_melhor", "soma", "Vendas",
       "Σ cupons das reduções Z do período.", ["pos_daily"], pdv_cupons, decimals=0),
    _m("pdv_ticket_medio", "Ticket médio do PDV", "R$", "maior_melhor", "media", "Vendas",
       "Venda bruta das reduções Z ÷ cupons.", ["pos_daily"], pdv_ticket_medio),
    _m("titulos_prorrogados", "Títulos prorrogados", "un", "menor_melhor", "soma", "Financeiro",
       "Títulos com DTVENCANTERIOR no período.", ["title_receivable"], titulos_prorrogados, decimals=0),
    _m("desconto_na_baixa", "Desconto concedido na baixa", "R$", "menor_melhor", "soma", "Financeiro",
       "Σ PCPREST.VALORDESC dos títulos pagos no período.", ["title_receivable"], desconto_na_baixa),
    _m("pagar_sem_dupla_autorizacao", "Títulos a pagar sem dupla autorização", "un", "menor_melhor", "ultimo", "Financeiro",
       "A pagar em aberto sem CODFUNCAUTOR1 e CODFUNCAUTOR2.", ["title_payable"], pagar_sem_dupla_autorizacao, decimals=0),
    _m("adiantamentos_fornecedor_aberto", "Adiantamentos a fornecedor em aberto", "R$", "menor_melhor", "ultimo", "Financeiro",
       "Adiantamentos pagos − valor já abatido em nota.", ["title_payable"], adiantamentos_fornecedor_aberto),
    _m("itens_sem_inventario_pct", "Itens sem inventário há +90 dias", "%", "menor_melhor", "ultimo", "Estoque",
       "Itens com saldo sem DTULTINVENT nos últimos 90 dias ÷ itens com saldo.", ["stock"], itens_sem_inventario_pct),
    _m("pedidos_compra_atrasados", "Pedidos de compra atrasados", "un", "menor_melhor", "ultimo", "Compras",
       "PCPEDIDO com DTPREVENT vencida e entrega incompleta.", ["purchase_order"], pedidos_compra_atrasados, decimals=0),
    _m("verba_fornecedor_aberta", "Verba de fornecedor a receber", "R$", "maior_melhor", "ultimo", "Compras",
       "PCVERBA sem quitação: VALOR − VPAGO.", ["supplier_credit"], verba_fornecedor_aberta),
    _m("ciclo_carga_horas", "Ciclo da carga (montagem → conferência)", "h", "menor_melhor", "media", "Logística",
       "Horas entre DATAMON e DATACONF das cargas expedidas.", ["load"], ciclo_carga_horas, decimals=1),
    _m("cargas_alem_prazo_rota", "Cargas além do prazo de rota", "un", "menor_melhor", "soma", "Logística",
       "Cargas cujo retorno passou de PCROTAEXP.PRAZOPREVENT dias.", ["load"], cargas_alem_prazo_rota, decimals=0),
    _m("nfe_denegadas", "NF-e denegadas ou rejeitadas", "un", "menor_melhor", "soma", "Fiscal",
       "PCNFSAID.SITUACAONFE em 110/205/301/302.", ["sales_invoice"], nfe_denegadas, decimals=0),
    _m("mdfe_pendentes", "MDF-e pendentes de transmissão", "un", "menor_melhor", "ultimo", "Fiscal",
       "MDF-e gerados sem protocolo e não cancelados.", ["mdfe"], mdfe_pendentes, decimals=0),
    _m("cnh_vencendo_30d", "CNH de motorista vencendo em 30 dias", "un", "menor_melhor", "ultimo", "Pessoas",
       "Motoristas ativos com DTVALIDADECNH até 30 dias à frente.", ["employee"], cnh_vencendo_30d, decimals=0),
    _m("usuarios_de_desligados", "Usuários ativos de funcionários desligados", "un", "menor_melhor", "ultimo", "Pessoas",
       "PCEMPR com DTDEMISSAO e USUARIOBD preenchido.", ["employee"], usuarios_de_desligados, decimals=0),
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
    # Força de vendas
    _m("valor_pedidos", "Venda transmitida (pedidos)", "R$", "maior_melhor", "soma", "Força de vendas",
       "Valor dos pedidos digitados no período, sem bonificação (PCPEDC.VLATEND).", ["order"], valor_pedidos),
    _m("pedidos_bloqueados_valor", "Venda bloqueada", "R$", "menor_melhor", "ultimo", "Força de vendas",
       "Pedidos pendentes na posição B (bloqueio comercial/financeiro).", ["order"], pedidos_bloqueados_valor),
    _m("pedidos_bloqueados_pct", "Pedidos bloqueados", "%", "menor_melhor", "media", "Força de vendas",
       "% dos pedidos do período que estão bloqueados.", ["order"], pedidos_bloqueados_pct),
    _m("comissao_valor", "Comissão gerada", "R$", "menor_melhor", "soma", "Força de vendas",
       "PERCOM × valor dos itens faturados.", ["sales_invoice_item"], comissao_valor),
    _m("comissao_pct", "Comissão sobre a venda", "%", "menor_melhor", "media", "Força de vendas",
       "Comissão gerada sobre o valor vendido nos itens.", ["sales_invoice_item"], comissao_pct),
    _m("clientes_curva_a_pct", "Clientes curva A", "%", "maior_melhor", "media", "Força de vendas",
       "% dos clientes positivados que fazem 80 % da venda.", ["sales_invoice"], clientes_curva_a_pct),
    _m("skus_curva_a_pct", "Produtos curva A", "%", "maior_melhor", "media", "Força de vendas",
       "% dos produtos vendidos que fazem 80 % da venda.", ["sales_invoice_item"], skus_curva_a_pct),
    _m("mix_por_cliente", "Mix por cliente", "un", "maior_melhor", "media", "Força de vendas",
       "Produtos distintos por cliente positivado.", ["sales_invoice_item"], mix_por_cliente, 1),
    _m("credito_disponivel_carteira", "Crédito disponível na carteira (aprox.)", "R$", "maior_melhor", "ultimo", "Força de vendas",
       "Limite − títulos em aberto − pedidos pendentes, somado nos clientes com limite.", ["customer", "title_receivable", "order"], credito_disponivel_carteira),
    _m("clientes_sem_credito_pct", "Clientes sem crédito disponível", "%", "menor_melhor", "ultimo", "Força de vendas",
       "% dos clientes com limite cujo crédito disponível está zerado.", ["customer", "title_receivable", "order"], clientes_sem_credito_pct),
    _m("clientes_positivados_delta", "Variação de positivados", "un", "maior_melhor", "soma", "Força de vendas",
       "Positivados no período menos os do período anterior.", ["sales_invoice"], clientes_positivados_delta, 0),
    # Carteira por RCA (aprendido do BI/geomarketing GEO)
    _m("clientes_perdidos_mes", "Clientes perdidos no mês", "un", "menor_melhor", "soma", "Força de vendas",
       "Positivados no mês anterior que não compraram neste mês.", ["sales_invoice"], clientes_perdidos_mes, 0),
    _m("rcas_sem_venda", "RCAs ativos sem venda", "un", "menor_melhor", "ultimo", "Força de vendas",
       "Vendedores ativos sem nota faturada no período.", ["salesrep", "sales_invoice"], rcas_sem_venda, 0),
    _m("carteira_positivada_pct", "Carteira positivada", "%", "maior_melhor", "media", "Força de vendas",
       "Positivados ÷ clientes da carteira (não bloqueados, com RCA).", ["sales_invoice", "customer"], carteira_positivada_pct),
    _m("carteira_inativa_pct", "Carteira inativa", "%", "menor_melhor", "ultimo", "Força de vendas",
       "% da carteira sem compra há mais de 90 dias.", ["customer"], carteira_inativa_pct),
    # WMS (PCMOVENDPEND agregada por OS)
    _m("wms_os_concluidas", "OS de separação concluídas", "un", "maior_melhor", "soma", "WMS",
       "Ordens de serviço de saída com separação concluída no período.", ["wms_os"], lambda t, i, f, fl=None: wms_os_concluidas(t, i, f, fl), 0),
    _m("wms_tempo_separacao_min", "Tempo médio de separação", "min", "menor_melhor", "media", "WMS",
       "Minutos entre início e fim da separação por OS, ponderado por linhas.", ["wms_os"], lambda t, i, f, fl=None: wms_tempo_separacao_min(t, i, f, fl), 1),
    _m("wms_tempo_conferencia_min", "Tempo médio de conferência", "min", "menor_melhor", "media", "WMS",
       "Minutos entre início e fim da conferência por OS.", ["wms_os"], lambda t, i, f, fl=None: wms_tempo_conferencia_min(t, i, f, fl), 1),
    _m("wms_os_pendentes", "OS de saída pendentes", "un", "menor_melhor", "ultimo", "WMS",
       "OS de saída abertas (sem fim de separação) no fim do período.", ["wms_os"], lambda t, i, f, fl=None: wms_os_pendentes(t, i, f, fl), 0),
    _m("wms_linhas_por_hora", "Linhas separadas por hora", "un", "maior_melhor", "media", "WMS",
       "Linhas de OS concluídas ÷ horas de separação.", ["wms_os"], lambda t, i, f, fl=None: wms_linhas_por_hora(t, i, f, fl), 1),
    _m("wms_corte_pct", "Corte na separação", "%", "menor_melhor", "media", "WMS",
       "Quantidade cancelada/cortada sobre a quantidade pedida nas OS.", ["wms_os"], lambda t, i, f, fl=None: wms_corte_pct(t, i, f, fl)),
    _m("wms_erros_conferencia", "Erros de conferência", "un", "menor_melhor", "soma", "WMS",
       "Erros apontados na conferência das OS (QTERROS).", ["wms_os"], lambda t, i, f, fl=None: wms_erros_conferencia(t, i, f, fl), 0),
    # Entrega direto do WinThor (PCCARREG)
    _m("entregas_por_carga", "Entregas por carga", "un", "maior_melhor", "media", "Logística",
       "PCCARREG.NUMENT (clientes distintos) por carga.", ["load"], entregas_por_carga, 1),
    _m("cidades_por_carga_erp", "Praças por carga", "un", "menor_melhor", "media", "Logística",
       "PCCARREG.NUMCID (praças distintas) por carga.", ["load"], cidades_por_carga_erp, 1),
    _m("km_por_carga", "Km rodados por carga", "km", "menor_melhor", "media", "Logística",
       "KMFINAL − KMINICIAL do acerto, nas cargas com odômetro.", ["load"], km_por_carga, 1),
    _m("km_por_entrega", "Km por entrega", "km", "menor_melhor", "media", "Logística",
       "Km rodados ÷ notas entregues.", ["load"], km_por_entrega),
    _m("cargas_sem_km_pct", "Cargas sem odômetro no acerto", "%", "menor_melhor", "media", "Logística",
       "Cargas retornadas sem KMFINAL preenchido.", ["load"], cargas_sem_km_pct),
    # Roteirização (FusionTrak)
    _m("cargas_roteirizadas_pct", "Cargas roteirizadas", "%", "maior_melhor", "media", "Roteirização",
       "Cargas expedidas que passaram pelo roteirizador.", ["route_load", "load"], lambda t, i, f, fl=None: cargas_roteirizadas_pct(t, i, f, fl)),
    _m("ocupacao_peso_pct", "Ocupação do veículo (peso)", "%", "maior_melhor", "media", "Roteirização",
       "Peso da carga sobre o peso máximo do veículo, nas cargas roteirizadas.", ["route_load"], lambda t, i, f, fl=None: ocupacao_peso_pct(t, i, f, fl)),
    _m("entregas_por_carga_roteirizada", "Entregas por carga roteirizada", "un", "maior_melhor", "media", "Roteirização",
       "Clientes por carga no roteirizador.", ["route_load"], lambda t, i, f, fl=None: entregas_por_carga_roteirizada(t, i, f, fl), 1),
    _m("cidades_por_carga", "Cidades por carga", "un", "menor_melhor", "media", "Roteirização",
       "Cidades atendidas por carga roteirizada.", ["route_load"], lambda t, i, f, fl=None: cidades_por_carga(t, i, f, fl), 1),
    _m("ocorrencias_entrega", "Ocorrências de entrega", "un", "menor_melhor", "soma", "Roteirização",
       "Eventos de entrega com ocorrência (recusa, devolução, reentrega) no período.", ["delivery_event"], lambda t, i, f, fl=None: ocorrencias_entrega(t, i, f, fl), 0),
    _m("entregas_com_ocorrencia_pct", "Entregas com ocorrência", "%", "menor_melhor", "media", "Roteirização",
       "Pedidos com evento de ocorrência sobre pedidos entregues.", ["delivery_event"], lambda t, i, f, fl=None: entregas_com_ocorrencia_pct(t, i, f, fl)),
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
