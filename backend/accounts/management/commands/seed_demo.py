"""Popula o banco com dados de demonstração (idempotente)."""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from accounts.models import OrgUnit, Tenant, User
from ai.models import AIInsight
from indicators.models import Indicator, IndicatorTarget, IndicatorValue
from plans.models import ActionItem, ActionPlan, Deviation
from strategy.models import Goal, Perspective, StrategicMap, StrategicObjective
from strategy.provisioning import create_default_perspectives

YEAR = 2026
SENHA = "demo1234"

# (code, name, unit, polarity, aggregation, area, targets jan..dez, values jan..ago)
KPIS = [
    ("REC", "Receita Mensal", "R$ mil", "maior_melhor", "soma", "Comercial",
     [1000] * 12, [1050, 980, 1100, 1020, 1150, 1080, 1200, 1130]),
    ("EBITDA", "Margem EBITDA", "%", "maior_melhor", "media", "Financeiro",
     [18] * 12, [19, 17.5, 18.2, 18.9, 17.8, 18.5, 19.2, 18.1]),
    ("NPS", "NPS", "pts", "maior_melhor", "ultimo", "Comercial",
     [70] * 12, [72, 68, 71, 73, 69, 70, 74, 71]),
    ("CHURN", "Churn de Clientes", "%", "menor_melhor", "media", "Comercial",
     [2] * 12, [1.8, 2.1, 1.9, 2.4, 2.6, 2.8, 3.1, 3.4]),
    ("OTIF", "OTIF - Entregas no Prazo", "%", "maior_melhor", "media", "Operações",
     [95] * 12, [96, 94, 93, 90, 88, 85, 83, 80]),
    ("TURN", "Turnover", "%", "menor_melhor", "media", "Pessoas",
     [3] * 12, [2.5, 2.8, 2.6, 2.9, 3.1, 2.7, 2.4, 2.8]),
    ("TKT", "Ticket Médio", "R$", "maior_melhor", "media", "Comercial",
     [850] * 12, [870, 830, 890, 860, 910, 880, 920, 900]),
    ("CPP", "Custo por Pedido", "R$", "menor_melhor", "media", "Operações",
     [45] * 12, [43, 44, 46, 42, 44, 43, 41, 44]),
    ("ABS", "Absenteísmo", "%", "menor_melhor", "media", "Pessoas",
     [2.5] * 12, [2.2, 2.4, 2.3, 2.6, 2.4, 2.2, 2.1, 2.3]),
    ("NCLI", "Novos Clientes", "un", "maior_melhor", "soma", "Comercial",
     [25] * 12, [28, 24, 27, 26, 30, 23, 29, 27]),
]

OBJECTIVES = {
    "Financeira": ["Crescer receita 20% ao ano", "Aumentar margem EBITDA"],
    "Clientes": ["Ser referência em satisfação do cliente", "Reduzir churn"],
    "Processos Internos": ["Excelência operacional nas entregas", "Reduzir custo por pedido"],
    "Aprendizado e Crescimento": ["Reter e desenvolver talentos", "Cultura orientada a dados"],
}

OBJECTIVE_LINKS = [
    ("Reter e desenvolver talentos", "Excelência operacional nas entregas"),
    ("Cultura orientada a dados", "Reduzir custo por pedido"),
    ("Excelência operacional nas entregas", "Ser referência em satisfação do cliente"),
    ("Reduzir custo por pedido", "Aumentar margem EBITDA"),
    ("Ser referência em satisfação do cliente", "Crescer receita 20% ao ano"),
    ("Reduzir churn", "Crescer receita 20% ao ano"),
]

KPI_OBJECTIVE = {
    "REC": "Crescer receita 20% ao ano", "TKT": "Crescer receita 20% ao ano",
    "NCLI": "Crescer receita 20% ao ano", "EBITDA": "Aumentar margem EBITDA",
    "NPS": "Ser referência em satisfação do cliente", "CHURN": "Reduzir churn",
    "OTIF": "Excelência operacional nas entregas", "CPP": "Reduzir custo por pedido",
    "TURN": "Reter e desenvolver talentos", "ABS": "Reter e desenvolver talentos",
}


class Command(BaseCommand):
    help = "Popula o banco com dados de demonstração"

    def handle(self, *args, **options):
        root, _ = User.objects.get_or_create(
            email="root@techsys.local",
            defaults={"first_name": "Root", "role": User.Role.ROOT,
                      "is_staff": True, "is_superuser": True},
        )
        root.set_password(SENHA)
        root.save()

        tenant, _ = Tenant.objects.get_or_create(
            name="Acme Indústria", slug="acme", defaults={"cnpj": "12.345.678/0001-90"}
        )

        def make_user(email, name, role, cargo, unit=None):
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={"first_name": name, "tenant": tenant, "role": role, "cargo": cargo},
            )
            user.set_password(SENHA)
            user.org_unit = unit
            user.save()
            return user

        admin = make_user("admin@acme.com", "Ana Admin", User.Role.ADMIN, "Diretora de Gestão")

        empresa, _ = OrgUnit.objects.get_or_create(
            tenant=tenant, name="Acme Indústria", kind="empresa", parent=None
        )
        areas = {}
        for i, name in enumerate(["Comercial", "Operações", "Financeiro", "Pessoas"]):
            areas[name], _ = OrgUnit.objects.get_or_create(
                tenant=tenant, name=name, kind="area", parent=empresa, defaults={"order": i}
            )
        vendas_sp, _ = OrgUnit.objects.get_or_create(
            tenant=tenant, name="Time Vendas SP", kind="time", parent=areas["Comercial"]
        )

        gestor = make_user("gestor@acme.com", "Gabriel Gestor", User.Role.GESTOR,
                           "Gerente Comercial", areas["Comercial"])
        colab1 = make_user("carla@acme.com", "Carla Colaboradora", User.Role.COLABORADOR,
                           "Vendedora", vendas_sp)
        make_user("caio@acme.com", "Caio Colaborador", User.Role.COLABORADOR,
                  "Analista de Operações", areas["Operações"])
        areas["Comercial"].manager = gestor
        areas["Comercial"].save()

        smap, created = StrategicMap.objects.get_or_create(
            tenant=tenant, name=f"Planejamento Estratégico {YEAR}",
            defaults={
                "year_start": YEAR, "year_end": YEAR + 2,
                "mission": "Entregar produtos industriais com excelência e agilidade.",
                "vision": "Ser líder regional do segmento até 2028.",
                "values_text": "Cliente no centro; Dados antes de opinião; Melhoria contínua.",
            },
        )
        create_default_perspectives(smap)

        objectives = {}
        for pname, objs in OBJECTIVES.items():
            perspective = smap.perspectives.get(name=pname)
            for order, oname in enumerate(objs):
                objectives[oname], _ = StrategicObjective.objects.get_or_create(
                    tenant=tenant, perspective=perspective, name=oname,
                    defaults={"owner": admin if pname == "Financeira" else gestor, "order": order},
                )
        for src, dst in OBJECTIVE_LINKS:
            objectives[src].contributes_to.add(objectives[dst])

        indicators = {}
        for code, name, unit, polarity, aggregation, area, targets, values in KPIS:
            ind, _ = Indicator.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={
                    "name": name, "unit": unit, "polarity": polarity,
                    "aggregation": aggregation, "org_unit": areas[area],
                    "owner": gestor if area == "Comercial" else admin,
                    "objective": objectives[KPI_OBJECTIVE[code]],
                },
            )
            indicators[code] = ind
            for month, target in enumerate(targets, start=1):
                IndicatorTarget.objects.update_or_create(
                    indicator=ind, period=date(YEAR, month, 1),
                    defaults={"target_value": Decimal(str(target))},
                )
            for month, value in enumerate(values, start=1):
                obj, _ = IndicatorValue.objects.update_or_create(
                    indicator=ind, period=date(YEAR, month, 1),
                    defaults={"value": Decimal(str(value)), "entered_by": gestor},
                )

        goal_empresa, _ = Goal.objects.get_or_create(
            tenant=tenant, name="Crescer receita 20% em 2026",
            defaults={"level": "empresa", "org_unit": empresa, "owner": admin,
                      "objective": objectives["Crescer receita 20% ao ano"],
                      "indicator": indicators["REC"]},
        )
        goal_area, _ = Goal.objects.get_or_create(
            tenant=tenant, name="Comercial: R$ 12,6 mi no ano",
            defaults={"level": "area", "parent": goal_empresa,
                      "org_unit": areas["Comercial"], "owner": gestor,
                      "indicator": indicators["REC"]},
        )
        goal_time, _ = Goal.objects.get_or_create(
            tenant=tenant, name="Vendas SP: 40% da receita da área",
            defaults={"level": "time", "parent": goal_area,
                      "org_unit": vendas_sp, "owner": gestor},
        )
        Goal.objects.get_or_create(
            tenant=tenant, name="Carla: 30 novos clientes no ano",
            defaults={"level": "pessoa", "parent": goal_time,
                      "org_unit": vendas_sp, "owner": colab1,
                      "indicator": indicators["NCLI"]},
        )

        # Desvio tratado (OTIF de junho) com plano concluído
        otif_jun = IndicatorValue.objects.get(indicator=indicators["OTIF"], period=date(YEAR, 6, 1))
        dev_jun = getattr(otif_jun, "deviation", None)
        if dev_jun and not dev_jun.action_plans.exists():
            dev_jun.root_cause = ("Atraso do transportador contratado na rota interior; "
                                  "janela de expedição subdimensionada na 2ª quinzena.")
            dev_jun.status = Deviation.Status.CONCLUIDO
            dev_jun.save()
            plano_ok = ActionPlan.objects.create(
                tenant=tenant, title="Recuperar OTIF - contratação de rota alternativa",
                what="Contratar transportadora alternativa para a rota interior.",
                why="OTIF em queda por atrasos recorrentes do transportador atual.",
                where="Expedição / Logística", who=admin,
                when_start=date(YEAR, 7, 1), when_end=date(YEAR, 7, 31),
                how="Cotação com 3 transportadoras, piloto de 2 semanas, contrato mensal.",
                how_much=Decimal("15000"), status=ActionPlan.Status.CONCLUIDO,
                pdca_stage=ActionPlan.PdcaStage.ACT, origin=ActionPlan.Origin.DESVIO,
                deviation=dev_jun, indicator=indicators["OTIF"], org_unit=areas["Operações"],
                priority=ActionPlan.Priority.ALTA,
            )
            for i, (t, s) in enumerate([
                ("Cotar 3 transportadoras", "feito"),
                ("Rodar piloto de 2 semanas", "feito"),
                ("Assinar contrato mensal", "feito"),
            ]):
                ActionItem.objects.create(plan=plano_ok, title=t, status=s, order=i,
                                          responsible=admin)

        # Desvio aberto em tratamento (CHURN de agosto) com plano em andamento
        churn_ago = IndicatorValue.objects.get(indicator=indicators["CHURN"], period=date(YEAR, 8, 1))
        dev_churn = getattr(churn_ago, "deviation", None)
        if dev_churn and not dev_churn.action_plans.exists():
            dev_churn.root_cause = "Aumento de cancelamentos após reajuste de preço em julho."
            dev_churn.status = Deviation.Status.EM_TRATAMENTO
            dev_churn.save()
            plano_churn = ActionPlan.objects.create(
                tenant=tenant, title="Conter churn pós-reajuste",
                what="Programa de retenção para clientes impactados pelo reajuste.",
                why="Churn subiu de 2,4% para 3,4% após reajuste de julho.",
                where="Carteira de clientes ativos", who=gestor,
                when_start=date(YEAR, 9, 1), when_end=date(YEAR, 10, 31),
                how="Réguas de contato, oferta de fidelização 12 meses, war room semanal.",
                how_much=Decimal("8000"), status=ActionPlan.Status.EM_ANDAMENTO,
                pdca_stage=ActionPlan.PdcaStage.DO, origin=ActionPlan.Origin.DESVIO,
                deviation=dev_churn, indicator=indicators["CHURN"],
                org_unit=areas["Comercial"], priority=ActionPlan.Priority.ALTA,
            )
            for i, (t, s) in enumerate([
                ("Mapear clientes em risco", "feito"),
                ("Lançar oferta de fidelização", "fazendo"),
                ("War room semanal de retenção", "a_fazer"),
            ]):
                ActionItem.objects.create(plan=plano_churn, title=t, status=s, order=i,
                                          responsible=gestor)

        ActionPlan.objects.get_or_create(
            tenant=tenant, title="Implantar dashboard de dados por área",
            defaults={
                "what": "Publicar dashboards mensais por área no TechSys Gestão.",
                "why": "Suportar o objetivo 'Cultura orientada a dados'.",
                "where": "Todas as áreas", "who": admin,
                "when_start": date(YEAR, 9, 1), "when_end": date(YEAR, 11, 30),
                "how": "Definir KPIs por área, treinar gestores, ritual mensal de resultados.",
                "status": ActionPlan.Status.EM_ANDAMENTO,
                "pdca_stage": ActionPlan.PdcaStage.PLAN,
                "objective": objectives["Cultura orientada a dados"],
                "org_unit": empresa, "priority": ActionPlan.Priority.MEDIA,
            },
        )

        AIInsight.objects.get_or_create(
            tenant=tenant, kind=AIInsight.Kind.ANALISE_INDICADOR,
            indicator=indicators["OTIF"], period=date(YEAR, 8, 1),
            defaults={
                "status": AIInsight.Status.CONCLUIDO, "requested_by": admin,
                "content": (
                    "## Análise do indicador OTIF\n\n"
                    "**Tendência**: queda consistente desde março (96% → 80%), "
                    "8,3 p.p. abaixo da meta em agosto.\n\n"
                    "**Riscos**: perda de clientes-chave por atraso recorrente; "
                    "impacto direto no NPS e no churn.\n\n"
                    "**Recomendações**: 1) revisar capacidade de expedição na 2ª quinzena; "
                    "2) monitorar SLA do novo transportador contratado em julho; "
                    "3) criar alerta semanal enquanto o indicador estiver vermelho.\n\n"
                    "*Exemplo de insight gerado por IA (pré-gravado no seed).*"
                ),
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"Seed concluído.\n"
            f"  root:   root@techsys.local / {SENHA}\n"
            f"  admin:  admin@acme.com / {SENHA}\n"
            f"  gestor: gestor@acme.com / {SENHA}\n"
            f"  colab:  carla@acme.com / {SENHA}"
        ))
