"""Monta contexto compacto (JSON-serializável) dos resultados do tenant para a IA."""
from datetime import date


def indicator_series(indicator, year=None):
    year = year or date.today().year
    targets = {t.period: t.target_value for t in indicator.targets.filter(period__year=year)}
    rows = []
    for v in indicator.values.filter(period__year=year).order_by("period"):
        rows.append({
            "periodo": v.period.strftime("%Y-%m"),
            "meta": targets.get(v.period),
            "realizado": v.value,
            "atingimento_pct": v.achievement_pct,
            "farol": v.status,
        })
    return rows


def tenant_results_context(tenant, year=None):
    from indicators.models import Indicator
    from plans.models import ActionPlan, Deviation

    year = year or date.today().year
    indicators = []
    for ind in Indicator.objects.filter(tenant=tenant, is_active=True).select_related("org_unit"):
        last = ind.values.filter(period__year=year).order_by("-period").first()
        indicators.append({
            "codigo": ind.code,
            "nome": ind.name,
            "area": ind.org_unit.name if ind.org_unit else None,
            "unidade": ind.unit,
            "polaridade": ind.polarity,
            "ultimo_periodo": last.period.strftime("%Y-%m") if last else None,
            "ultimo_realizado": last.value if last else None,
            "ultimo_atingimento_pct": last.achievement_pct if last else None,
            "farol": last.status if last else None,
        })

    deviations = [
        {
            "indicador": d.indicator.code,
            "periodo": d.indicator_value.period.strftime("%Y-%m"),
            "status": d.status,
            "causa_raiz": d.root_cause or None,
        }
        for d in Deviation.objects.filter(tenant=tenant).select_related(
            "indicator", "indicator_value"
        )[:30]
    ]

    plans = [
        {
            "titulo": p.title,
            "status": p.status,
            "pdca": p.pdca_stage,
            "responsavel": p.who.first_name if p.who else None,
            "prazo": p.when_end.isoformat() if p.when_end else None,
        }
        for p in ActionPlan.objects.filter(tenant=tenant).select_related("who")[:30]
    ]

    return {
        "empresa": tenant.name,
        "ano": year,
        "indicadores": indicators,
        "desvios": deviations,
        "planos_de_acao": plans,
    }
