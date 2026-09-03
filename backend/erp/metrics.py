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
