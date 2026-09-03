"""Painel do ERP — um mini BI sobre o espelho, numa página só.

Objetivo: o gestor olhar o que o agente já trouxe (cobertura por entidade),
os números de negócio que saem disso (faturamento, margem, caixa, estoque…)
e CONFERIR cada indicador ligado ao ERP: o valor gravado no KPI × o valor
que o espelho dá agora. Se bater, o indicador está confiável; se não, ou a
carga avançou desde o último cálculo ou algo mudou na regra.

Tudo aqui é leitura. Nada grava.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Min, Sum
from django.utils import timezone

from indicators.models import Indicator

from . import metrics as m
from .models import (
    BankAccount,
    Branch,
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
    SalesRep,
    StockBalance,
    Supplier,
)
from .winthor import WINTHOR_QUERIES

D = Decimal
PLANO = {q["entity"]: q for q in WINTHOR_QUERIES}

# Entidade → (modelo, filtro extra, campo de data) para a cobertura.
COBERTURA = [
    ("branch", Branch, {}, None),
    ("salesrep", SalesRep, {}, None),
    ("supplier", Supplier, {}, None),
    ("employee", Employee, {}, "admission_date"),
    ("customer", Customer, {}, "last_purchase_at"),
    ("product", Product, {}, None),
    ("sales_invoice", SalesInvoice, {}, "issued_at"),
    ("sales_invoice_item", SalesInvoiceItem, {}, "moved_at"),
    ("title_receivable", FinancialTitle, {"kind": "receivable"}, "due_date"),
    ("title_payable", FinancialTitle, {"kind": "payable"}, "due_date"),
    ("financial_snapshot", FinancialSnapshot, {}, "date"),
    ("bank_account", BankAccount, {}, None),
    ("cash_movement", CashMovement, {}, "moved_at"),
    ("stock", StockBalance, {}, None),
    ("order", Order, {}, "order_date"),
    ("purchase", PurchaseInvoice, {}, "entry_date"),
    ("load", DeliveryLoad, {}, "departure_date"),
]

# O que vai na série mensal (chave do catálogo de métricas).
SERIE_MENSAL = [
    "faturamento", "cmv", "margem_bruta_pct", "qtd_notas", "ticket_medio",
    "positivacao", "recebido", "despesas_pagas", "compras_valor",
]

# Fotografia do mês corrente.
FOTO_MES = [
    "faturamento", "qtd_notas", "ticket_medio", "margem_bruta_pct", "positivacao",
    "a_receber_aberto", "a_receber_vencido", "inadimplencia_pct",
    "a_pagar_aberto", "a_pagar_vencido", "saldo_caixa",
    "estoque_valor", "ruptura_pct", "cobertura_estoque_dias",
    "carteira_pedidos", "headcount",
]

TOP_N = 10

_VALOR = ExpressionWrapper(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=18, decimal_places=4))
_CUSTO = ExpressionWrapper(F("quantity") * F("cost"), output_field=DecimalField(max_digits=18, decimal_places=4))


def _mes_anterior(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def _meses(qtd: int, ate: date):
    """Os últimos `qtd` meses (dia 1), do mais antigo ao corrente."""
    out, cur = [], ate.replace(day=1)
    for _ in range(qtd):
        out.append(cur)
        cur = _mes_anterior(cur)
    return list(reversed(out))


def _num(v):
    if v is None:
        return None
    return float(v)


def cobertura(tenant):
    linhas = []
    for entity, model, extra, campo in COBERTURA:
        qs = model.objects.filter(tenant=tenant, **extra)
        agg = {"total": Count("id")}
        if campo:
            agg["de"] = Min(campo)
            agg["ate"] = Max(campo)
        r = qs.aggregate(**agg)
        q = PLANO.get(entity, {})
        linhas.append({
            "entity": entity,
            "label": q.get("label", entity),
            "total": r["total"],
            "de": r.get("de"),
            "ate": r.get("ate"),
            "incremental": bool(q.get("incremental")),
        })
    return linhas


def serie_mensal(tenant, meses, filters):
    hoje = date.today()
    out = []
    for periodo in _meses(meses, hoje):
        linha = {"periodo": periodo}
        for key in SERIE_MENSAL:
            linha[key] = _num(m.compute_metric(key, tenant, periodo, filters))
        out.append(linha)
    return out


def foto_mes(tenant, filters):
    hoje = date.today()
    atual = {k: _num(m.compute_metric(k, tenant, hoje, filters)) for k in FOTO_MES}
    anterior = {k: _num(m.compute_metric(k, tenant, _mes_anterior(hoje), filters)) for k in ("faturamento", "qtd_notas", "ticket_medio", "margem_bruta_pct", "positivacao")}
    return {"periodo": hoje.replace(day=1), "atual": atual, "mes_anterior": anterior}


def por_filial(tenant):
    hoje = date.today()
    ini_mes, fim = m.month_bounds(hoje)
    fim = min(fim, hoje)
    ini_ano = hoje.replace(month=1, day=1)
    mes_map = {
        r["branch__code"]: (r["v"], r["n"])
        for r in m.notas_do_periodo(tenant, ini_mes, fim, {}).values("branch__code").annotate(v=Sum("total"), n=Count("id"))
    }
    ano_map = {
        r["branch__code"]: r["v"]
        for r in m.notas_do_periodo(tenant, ini_ano, fim, {}).values("branch__code").annotate(v=Sum("total"))
    }
    linhas = []
    for b in Branch.objects.filter(tenant=tenant).order_by("code"):
        v, n = mes_map.get(b.code, (None, 0))
        linhas.append({
            "code": b.code, "name": b.trade_name or b.name,
            "faturamento_mes": _num(v), "notas_mes": n, "faturamento_ano": _num(ano_map.get(b.code)),
        })
    return linhas


def rankings(tenant, filters):
    hoje = date.today()
    ini, fim = m.month_bounds(hoje)
    fim = min(fim, hoje)
    notas = m.notas_do_periodo(tenant, ini, fim, filters)
    vendedores = [
        {"name": r["sales_rep__name"] or "(sem vendedor)", "valor": _num(r["v"]), "notas": r["n"]}
        for r in notas.values("sales_rep__name").annotate(v=Sum("total"), n=Count("id")).order_by("-v")[:TOP_N]
    ]
    clientes = [
        {"name": r["customer__name"] or "(sem cliente)", "valor": _num(r["v"]), "notas": r["n"]}
        for r in notas.values("customer__name").annotate(v=Sum("total"), n=Count("id")).order_by("-v")[:TOP_N]
    ]
    itens = m._itens_venda(tenant, ini, fim, filters)
    departamentos = []
    for r in itens.values("product__department").annotate(v=Sum(_VALOR), c=Sum(_CUSTO)).order_by("-v")[:TOP_N]:
        v, c = r["v"], r["c"]
        departamentos.append({
            "name": r["product__department"] or "(sem departamento)",
            "valor": _num(v), "custo": _num(c),
            "margem_pct": _num(m._pct(D(v) - D(c or 0), v)) if v else None,
        })
    produtos = [
        {"name": r["product__name"], "valor": _num(r["v"]), "quantidade": _num(r["q"])}
        for r in itens.values("product__name").annotate(v=Sum(_VALOR), q=Sum("quantity")).order_by("-v")[:TOP_N]
    ]
    return {"periodo": ini, "vendedores": vendedores, "clientes": clientes, "departamentos": departamentos, "produtos": produtos}


def _entidades_carregadas(tenant):
    return {linha["entity"] for linha in cobertura(tenant) if linha["total"] > 0}


def conferencia(tenant, carregadas=None):
    """Para cada indicador ligado ao ERP: o gravado × o que o espelho dá agora."""
    carregadas = _entidades_carregadas(tenant) if carregadas is None else carregadas
    hoje = date.today()
    out = []
    qs = Indicator.objects.filter(tenant=tenant, is_active=True).exclude(erp_metric="").order_by("code")
    for ind in qs:
        metric = m.get_metric(ind.erp_metric)
        ultimo = ind.values.filter(source="agent").order_by("-period").first()
        periodo = ultimo.period if ultimo else hoje.replace(day=1)
        tem_dados = bool(metric) and all(e in carregadas for e in metric.entities)
        erp_agora = m.compute_metric(ind.erp_metric, tenant, periodo, ind.erp_filters) if tem_dados else None
        meta = ind.targets.filter(period=periodo).first()

        if metric is None:
            situacao = "metrica_invalida"
        elif not tem_dados:
            situacao = "sem_dados"
        elif ultimo is None:
            situacao = "aguardando"
        elif erp_agora is None:
            situacao = "sem_valor"
        else:
            q = D(1).scaleb(-ind.decimals)
            situacao = "confere" if D(ultimo.value).quantize(q) == D(erp_agora).quantize(q) else "divergente"

        out.append({
            "id": ind.id, "code": ind.code, "name": ind.name, "unit": ind.unit, "decimals": ind.decimals,
            "polarity": ind.polarity, "erp_metric": ind.erp_metric,
            "erp_metric_label": metric.label if metric else ind.erp_metric,
            "erp_filters": ind.erp_filters or {},
            "entities": metric.entities if metric else [],
            "periodo": periodo,
            "valor_gravado": _num(ultimo.value) if ultimo else None,
            "calculado_em": ultimo.updated_at if ultimo else None,
            "valor_erp": _num(erp_agora),
            "meta": _num(meta.target_value) if meta else None,
            "achievement_pct": _num(ultimo.achievement_pct) if ultimo else None,
            "status": ultimo.status if ultimo else None,
            "situacao": situacao,
        })
    return out


def painel(tenant, meses=12, branch=None):
    filters = {"branch": branch} if branch else {}
    cob = cobertura(tenant)
    carregadas = {linha["entity"] for linha in cob if linha["total"] > 0}
    confer = conferencia(tenant, carregadas)
    resumo = {
        "total": len(confer),
        "confere": sum(1 for c in confer if c["situacao"] == "confere"),
        "divergente": sum(1 for c in confer if c["situacao"] == "divergente"),
        "aguardando": sum(1 for c in confer if c["situacao"] == "aguardando"),
        "sem_dados": sum(1 for c in confer if c["situacao"] in ("sem_dados", "sem_valor", "metrica_invalida")),
    }
    return {
        "gerado_em": timezone.now(),
        "meses": meses,
        "filial": branch,
        "filiais": [{"code": b.code, "name": b.trade_name or b.name} for b in Branch.objects.filter(tenant=tenant).order_by("code")],
        "cobertura": cob,
        "serie": serie_mensal(tenant, meses, filters),
        "foto": foto_mes(tenant, filters),
        "por_filial": por_filial(tenant),
        "rankings": rankings(tenant, filters),
        "indicadores": confer,
        "resumo_conferencia": resumo,
    }
