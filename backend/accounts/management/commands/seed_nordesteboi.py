"""Cria a empresa Nordeste Boi (distribuição + varejo) com planejamento completo.

Idempotente. Cria tenant, admin, organograma, conector WinThor (com token),
mapa estratégico com objetivos e ligações de causa-efeito, e indicadores
LIGADOS ÀS MÉTRICAS DO ERP — assim que o agente subir dados, os faróis acendem.
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from accounts.models import OrgUnit, Tenant, User
from erp.coletor import new_token
from erp.metrics import get_metric
from erp.models import Connector
from indicators.models import DataSource, Indicator, IndicatorTarget
from strategy.models import Goal, StrategicObjective
from strategy.provisioning import bootstrap_tenant

YEAR = date.today().year
SENHA = "nordeste2026"

# Perspectiva -> objetivos
OBJECTIVES = {
    "Financeira": [
        "Crescer o faturamento com rentabilidade",
        "Proteger a margem bruta",
        "Reduzir a inadimplência e o ciclo de caixa",
    ],
    "Clientes": [
        "Ampliar e reter a base de clientes",
        "Ser a melhor entrega do mercado (nível de serviço)",
        "Crescer o mix por cliente",
    ],
    "Processos Internos": [
        "Zerar ruptura nos itens de giro",
        "Otimizar estoque e capital de giro",
        "Elevar a produtividade logística",
        "Disciplina comercial de preço e bonificação",
    ],
    "Aprendizado e Crescimento": [
        "Reter e engajar a equipe",
        "Gestão orientada por dados em tempo real",
    ],
}

# Causa -> efeito (sobe no mapa)
LINKS = [
    ("Reter e engajar a equipe", "Elevar a produtividade logística"),
    ("Gestão orientada por dados em tempo real", "Zerar ruptura nos itens de giro"),
    ("Gestão orientada por dados em tempo real", "Disciplina comercial de preço e bonificação"),
    ("Zerar ruptura nos itens de giro", "Ser a melhor entrega do mercado (nível de serviço)"),
    ("Elevar a produtividade logística", "Ser a melhor entrega do mercado (nível de serviço)"),
    ("Otimizar estoque e capital de giro", "Reduzir a inadimplência e o ciclo de caixa"),
    ("Disciplina comercial de preço e bonificação", "Proteger a margem bruta"),
    ("Ser a melhor entrega do mercado (nível de serviço)", "Ampliar e reter a base de clientes"),
    ("Crescer o mix por cliente", "Crescer o faturamento com rentabilidade"),
    ("Ampliar e reter a base de clientes", "Crescer o faturamento com rentabilidade"),
    ("Proteger a margem bruta", "Crescer o faturamento com rentabilidade"),
]

# (code, nome, métrica do ERP, área, objetivo, meta mensal, limite amarelo %)
# Metas são pontos de partida: o gestor ajusta na tela do indicador.
INDICATORS = [
    # Financeira
    ("FAT", "Faturamento líquido", "faturamento", "Comercial", "Crescer o faturamento com rentabilidade", 4_500_000, 90),
    ("FAT_CD", "Faturamento — distribuição (CD)", "faturamento", "Distribuição", "Crescer o faturamento com rentabilidade", 3_200_000, 90, {"branch": "1"}),
    ("FAT_LOJA", "Faturamento — varejo (lojas)", "faturamento", "Varejo", "Crescer o faturamento com rentabilidade", 1_300_000, 90, {"branch": "2"}),
    ("MARGEM", "Margem bruta", "margem_bruta_pct", "Financeiro", "Proteger a margem bruta", 22, 92),
    ("CMV", "CMV", "cmv", "Financeiro", "Proteger a margem bruta", 3_500_000, 95),
    ("DESP", "Despesas por competência", "despesas_competencia", "Financeiro", "Proteger a margem bruta", 650_000, 95),
    ("FOLHA", "Folha sobre faturamento", "folha_pct_faturamento", "Financeiro", "Proteger a margem bruta", 8, 90),
    ("INAD", "Inadimplência (+30 dias)", "inadimplencia_pct", "Financeiro", "Reduzir a inadimplência e o ciclo de caixa", 3, 85),
    ("PMR", "Prazo médio de recebimento", "prazo_medio_recebimento", "Financeiro", "Reduzir a inadimplência e o ciclo de caixa", 28, 90),
    ("RECVENC", "A receber vencido", "a_receber_vencido", "Financeiro", "Reduzir a inadimplência e o ciclo de caixa", 250_000, 85),
    ("CAIXA", "Saldo de caixa e bancos", "saldo_caixa", "Financeiro", "Reduzir a inadimplência e o ciclo de caixa", 800_000, 85),
    ("GERCX", "Geração de caixa", "geracao_caixa", "Financeiro", "Reduzir a inadimplência e o ciclo de caixa", 150_000, 80),
    # Clientes
    ("POSIT", "Clientes positivados", "positivacao", "Comercial", "Ampliar e reter a base de clientes", 1_800, 90),
    ("ATIVOS", "Clientes ativos (90 dias)", "clientes_ativos", "Comercial", "Ampliar e reter a base de clientes", 2_600, 92),
    ("NCLI", "Novos clientes", "novos_clientes", "Comercial", "Ampliar e reter a base de clientes", 60, 85),
    ("CHURN", "Churn de clientes", "churn_clientes_pct", "Comercial", "Ampliar e reter a base de clientes", 8, 85),
    ("TKT", "Ticket médio", "ticket_medio", "Comercial", "Crescer o mix por cliente", 2_400, 92),
    ("MIX", "Mix de produtos vendidos", "mix_skus", "Comercial", "Crescer o mix por cliente", 900, 90),
    ("DEVOL", "Devoluções sobre vendas", "devolucoes_pct", "Logística", "Ser a melhor entrega do mercado (nível de serviço)", 1.5, 80),
    ("CORTE", "Pedidos com corte", "corte_pct", "Logística", "Ser a melhor entrega do mercado (nível de serviço)", 5, 85),
    # Processos
    ("RUPT", "Ruptura nos itens de giro", "ruptura_pct", "Compras", "Zerar ruptura nos itens de giro", 4, 80),
    ("VPERD", "Venda perdida por falta", "venda_perdida_qtd", "Compras", "Zerar ruptura nos itens de giro", 500, 80),
    ("COBERT", "Cobertura de estoque", "cobertura_estoque_dias", "Compras", "Otimizar estoque e capital de giro", 18, 85),
    ("ESTQ", "Estoque a custo", "estoque_valor", "Compras", "Otimizar estoque e capital de giro", 2_800_000, 90),
    ("GIRO", "Giro de estoque", "giro_estoque", "Compras", "Otimizar estoque e capital de giro", 1.3, 90),
    ("COMPRAS", "Compras (entradas)", "compras_valor", "Compras", "Otimizar estoque e capital de giro", 3_300_000, 90),
    ("CARGAS", "Cargas expedidas", "cargas_expedidas", "Logística", "Elevar a produtividade logística", 320, 90),
    ("NFCARGA", "Notas por carga", "notas_por_carga", "Logística", "Elevar a produtividade logística", 22, 90),
    ("TON", "Peso entregue", "peso_entregue_ton", "Logística", "Elevar a produtividade logística", 1_100, 90),
    ("FRETE", "Frete sobre faturamento", "frete_pct_faturamento", "Logística", "Elevar a produtividade logística", 3.5, 85),
    ("DESC", "Desconto médio praticado", "desconto_medio_pct", "Comercial", "Disciplina comercial de preço e bonificação", 6, 85),
    ("BONIF", "Bonificação sobre faturamento", "bonificacao_pct", "Comercial", "Disciplina comercial de preço e bonificação", 1.2, 85),
    ("CONV", "Conversão pedido → nota", "conversao_pedido_nota_pct", "Comercial", "Disciplina comercial de preço e bonificação", 92, 95),
    ("CARTEIRA", "Carteira de pedidos", "carteira_pedidos", "Comercial", "Disciplina comercial de preço e bonificação", 600_000, 85),
    # Pessoas
    ("HC", "Headcount", "headcount", "Pessoas", "Reter e engajar a equipe", 180, 95),
    ("TURN", "Turnover", "turnover_pct", "Pessoas", "Reter e engajar a equipe", 2.5, 85),
    ("DESLIG", "Desligamentos", "desligamentos", "Pessoas", "Reter e engajar a equipe", 4, 80),
    # Manuais (o ERP não mede)
    ("NPS", "NPS", "", "Comercial", "Ser a melhor entrega do mercado (nível de serviço)", 70, 90),
    ("ABS", "Absenteísmo", "", "Pessoas", "Reter e engajar a equipe", 2.5, 85),
    ("TREIN", "Horas de treinamento", "", "Pessoas", "Gestão orientada por dados em tempo real", 8, 85),
]

AREAS = ["Comercial", "Distribuição", "Varejo", "Logística", "Compras", "Financeiro", "Pessoas"]


class Command(BaseCommand):
    help = "Cria a empresa Nordeste Boi com planejamento estratégico ligado ao ERP"

    def handle(self, *args, **options):
        tenant, created = Tenant.objects.get_or_create(
            slug="nordesteboi", defaults={"name": "Nordeste Boi"}
        )
        prov = bootstrap_tenant(tenant, year=YEAR)
        root_unit = prov["org_unit"]
        smap = prov["map"]
        smap.mission = "Levar carne de qualidade do frigorífico à mesa do Nordeste, com entrega confiável e preço justo."
        smap.vision = f"Ser a distribuidora de proteína mais eficiente do Nordeste até {YEAR + 2}, com lojas próprias referência em atendimento."
        smap.values_text = "Confiança; Agilidade; Dados antes de opinião; Respeito ao cliente e à equipe."
        smap.save()

        admin, _ = User.objects.get_or_create(
            email="admin@nordesteboi.com.br",
            defaults={"first_name": "Gestão Nordeste Boi", "tenant": tenant,
                      "role": User.Role.ADMIN, "org_unit": root_unit, "cargo": "Diretoria"},
        )
        admin.set_password(SENHA)
        admin.save()

        areas = {}
        for i, name in enumerate(AREAS):
            areas[name], _ = OrgUnit.objects.get_or_create(
                tenant=tenant, name=name, kind="area", parent=root_unit, defaults={"order": i}
            )

        # Conector WinThor (perfil misto: distribuição + varejo)
        connector, created_conn = Connector.objects.get_or_create(
            tenant=tenant, name="WinThor Nordeste Boi",
            defaults={"erp": Connector.Erp.WINTHOR, "perfil": Connector.Perfil.MISTO,
                      "ingest_token": new_token()},
        )
        data_source = DataSource.objects.filter(tenant=tenant, type=DataSource.Type.AGENT).first()

        # Objetivos + ligações
        objectives = {}
        for pname, names in OBJECTIVES.items():
            perspective = smap.perspectives.filter(name=pname).first()
            if perspective is None:
                continue
            for order, oname in enumerate(names):
                objectives[oname], _ = StrategicObjective.objects.get_or_create(
                    tenant=tenant, perspective=perspective, name=oname,
                    defaults={"owner": admin, "order": order},
                )
        for src, dst in LINKS:
            if src in objectives and dst in objectives:
                objectives[src].contributes_to.add(objectives[dst])

        # Indicadores ligados ao ERP
        criados = 0
        for row in INDICATORS:
            code, name, metric_key, area, objective, meta, amarelo = row[:7]
            filters = row[7] if len(row) > 7 else {}
            metric = get_metric(metric_key) if metric_key else None
            defaults = {
                "name": name,
                "unit": metric.unit if metric else ("pts" if code == "NPS" else "%" if code == "ABS" else "h"),
                "decimals": metric.decimals if metric else (0 if code == "NPS" else 1),
                "polarity": metric.polarity if metric else ("menor_melhor" if code == "ABS" else "maior_melhor"),
                "aggregation": metric.aggregation if metric else ("ultimo" if code == "NPS" else "media" if code == "ABS" else "soma"),
                "org_unit": areas.get(area, root_unit),
                "owner": admin,
                "objective": objectives.get(objective),
                "data_source": data_source if metric else None,
                "erp_metric": metric_key,
                "erp_filters": filters,
                "yellow_threshold_pct": Decimal(str(amarelo)),
                "description": metric.description if metric else "",
            }
            ind, was_created = Indicator.objects.update_or_create(
                tenant=tenant, code=code, defaults=defaults
            )
            criados += int(was_created)
            for month in range(1, 13):
                IndicatorTarget.objects.get_or_create(
                    indicator=ind, period=date(YEAR, month, 1),
                    defaults={"target_value": Decimal(str(meta))},
                )

        # Metas em cascata (empresa -> áreas)
        fat = Indicator.objects.get(tenant=tenant, code="FAT")
        goal_empresa, _ = Goal.objects.get_or_create(
            tenant=tenant, name=f"Faturar R$ 54 mi em {YEAR} com margem ≥ 22%",
            defaults={"level": "empresa", "org_unit": root_unit, "owner": admin,
                      "objective": objectives.get("Crescer o faturamento com rentabilidade"),
                      "indicator": fat},
        )
        for area_name, code, nome in (
            ("Distribuição", "FAT_CD", "CD: R$ 38,4 mi no ano"),
            ("Varejo", "FAT_LOJA", "Lojas: R$ 15,6 mi no ano"),
            ("Compras", "RUPT", "Ruptura abaixo de 4% todo mês"),
            ("Logística", "CORTE", "Corte de pedidos abaixo de 5%"),
            ("Financeiro", "INAD", "Inadimplência abaixo de 3%"),
        ):
            Goal.objects.get_or_create(
                tenant=tenant, name=nome,
                defaults={"level": "area", "parent": goal_empresa, "org_unit": areas[area_name],
                          "owner": admin, "indicator": Indicator.objects.get(tenant=tenant, code=code)},
            )

        self.stdout.write(self.style.SUCCESS(
            f"Nordeste Boi pronta.\n"
            f"  login : admin@nordesteboi.com.br / {SENHA}\n"
            f"  áreas : {', '.join(AREAS)}\n"
            f"  mapa  : {sum(len(v) for v in OBJECTIVES.values())} objetivos, {len(LINKS)} ligações\n"
            f"  KPIs  : {len(INDICATORS)} indicadores ({sum(1 for r in INDICATORS if r[2])} ligados ao ERP), {criados} novos\n"
            f"  token do agente: {connector.ingest_token}\n"
            f"  (o comando de instalação e o script do DBA estão em Integrações → Conector ERP)"
        ))
