"""Provisionamento inicial de uma empresa (tenant).

As perspectivas do mapa NÃO são fixas no código: elas viram linhas no banco e o
administrador da empresa pode renomear, recolorir, reordenar, criar e excluir.
A lista abaixo é apenas o **modelo padrão** aplicado quando uma empresa nasce ou
quando um mapa novo é criado sem perspectivas — o BSC clássico como ponto de
partida, não como camisa de força.
"""
from datetime import date

DEFAULT_PERSPECTIVES = [
    {"name": "Financeira", "color": "#198754"},
    {"name": "Clientes", "color": "#2a78d6"},
    {"name": "Processos Internos", "color": "#eb6834"},
    {"name": "Aprendizado e Crescimento", "color": "#6f42c1"},
]

# Catálogo inicial de KPIs — genéricos e comuns a qualquer empresa. Também é só
# um ponto de partida: o gestor renomeia, ajusta polaridade/agregação, cria os
# seus e exclui o que não usar.
DEFAULT_INDICATORS = [
    # Financeira
    {"code": "REC", "name": "Receita", "unit": "R$", "polarity": "maior_melhor",
     "aggregation": "soma", "decimals": 2},
    {"code": "MARGEM", "name": "Margem de Contribuição", "unit": "%",
     "polarity": "maior_melhor", "aggregation": "media", "decimals": 2},
    {"code": "DESP", "name": "Despesa Operacional", "unit": "R$",
     "polarity": "menor_melhor", "aggregation": "soma", "decimals": 2},
    # Clientes
    {"code": "NPS", "name": "NPS", "unit": "pts", "polarity": "maior_melhor",
     "aggregation": "ultimo", "decimals": 0},
    {"code": "CHURN", "name": "Churn de Clientes", "unit": "%",
     "polarity": "menor_melhor", "aggregation": "media", "decimals": 2},
    {"code": "NCLI", "name": "Novos Clientes", "unit": "un",
     "polarity": "maior_melhor", "aggregation": "soma", "decimals": 0},
    # Processos internos
    {"code": "OTIF", "name": "Entregas no Prazo (OTIF)", "unit": "%",
     "polarity": "maior_melhor", "aggregation": "media", "decimals": 2},
    {"code": "RETRAB", "name": "Índice de Retrabalho", "unit": "%",
     "polarity": "menor_melhor", "aggregation": "media", "decimals": 2},
    # Aprendizado e crescimento
    {"code": "TURN", "name": "Turnover", "unit": "%", "polarity": "menor_melhor",
     "aggregation": "media", "decimals": 2},
    {"code": "ABS", "name": "Absenteísmo", "unit": "%", "polarity": "menor_melhor",
     "aggregation": "media", "decimals": 2},
    {"code": "TREIN", "name": "Horas de Treinamento", "unit": "h",
     "polarity": "maior_melhor", "aggregation": "soma", "decimals": 1},
]


def create_default_perspectives(strategic_map):
    """Cria as perspectivas padrão em um mapa. Idempotente: não duplica."""
    from .models import Perspective

    if strategic_map.perspectives.exists():
        return list(strategic_map.perspectives.all())

    return [
        Perspective.objects.create(
            map=strategic_map,
            name=item["name"],
            color=item["color"],
            order=index,
        )
        for index, item in enumerate(DEFAULT_PERSPECTIVES)
    ]


def create_default_indicators(tenant, org_unit=None, owner=None):
    """Cria o catálogo padrão de KPIs. Idempotente: pula códigos já existentes.

    Nasce sem meta e sem lançamento — o gestor define as metas do ano na tela do
    indicador. Só os códigos que faltam são criados, então dá para chamar de novo
    depois de o usuário ter excluído ou criado os seus.
    """
    from indicators.models import Indicator

    existing = set(
        Indicator.objects.filter(tenant=tenant).values_list("code", flat=True)
    )
    created = [
        Indicator.objects.create(
            tenant=tenant,
            code=item["code"],
            name=item["name"],
            unit=item["unit"],
            polarity=item["polarity"],
            aggregation=item["aggregation"],
            decimals=item["decimals"],
            org_unit=org_unit,
            owner=owner,
        )
        for item in DEFAULT_INDICATORS
        if item["code"] not in existing
    ]
    return created


def bootstrap_tenant(tenant, *, year=None):
    """Deixa uma empresa nova pronta para uso.

    Cria a unidade organizacional raiz, o mapa estratégico ativo do ano e as
    perspectivas padrão. Idempotente — pode rodar de novo sem duplicar nada.
    """
    from accounts.models import OrgUnit

    from .models import StrategicMap

    year = year or date.today().year

    org_unit, _ = OrgUnit.objects.get_or_create(
        tenant=tenant,
        parent=None,
        kind=OrgUnit.Kind.EMPRESA,
        defaults={"name": tenant.name},
    )

    strategic_map = StrategicMap.objects.filter(tenant=tenant, is_active=True).first()
    if strategic_map is None:
        strategic_map = StrategicMap.objects.create(
            tenant=tenant,
            name=f"Planejamento Estratégico {year}",
            year_start=year,
            year_end=year + 2,
        )

    perspectives = create_default_perspectives(strategic_map)
    indicators = create_default_indicators(tenant, org_unit=org_unit)
    return {
        "org_unit": org_unit,
        "map": strategic_map,
        "perspectives": perspectives,
        "indicators": indicators,
    }
