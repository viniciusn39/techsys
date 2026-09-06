"""Semeia/atualiza o catálogo de KPIs do WinThor em KpiTemplate (idempotente).

Roda no deploy (entrypoint) e pode rodar à mão. Campos que o catálogo não
define (unidade, polaridade, agregação, casas) vêm da métrica do espelho.
Um modelo que saiu do catálogo é desativado, não apagado.
"""
from django.core.management.base import BaseCommand

from erp.catalogo_winthor import CATALOGO
from erp.metrics import get_metric
from erp.models import KpiTemplate
from erp.targets import get_target_source


class Command(BaseCommand):
    help = "Semeia o catálogo de KPIs do WinThor (KpiTemplate)."

    def handle(self, *args, **options):
        criados = atualizados = 0
        vistos = set()
        for ordem, item in enumerate(CATALOGO):
            metric = get_metric(item["erp_metric"]) if item["erp_metric"] else None
            if item["erp_metric"] and metric is None:
                raise SystemExit(f"{item['code']}: métrica '{item['erp_metric']}' não existe em erp.metrics")
            if item["erp_target"] and get_target_source(item["erp_target"]) is None:
                raise SystemExit(f"{item['code']}: fonte de meta '{item['erp_target']}' não existe em erp.targets")
            campos = {
                "name": item["name"], "sector": item["sector"], "perspective": item["perspective"],
                "unit": item["unit"] if item["unit"] is not None else (metric.unit if metric else ""),
                "decimals": item["decimals"] if item["decimals"] is not None else (metric.decimals if metric else 2),
                "polarity": item["polarity"] or (metric.polarity if metric else "maior_melhor"),
                "aggregation": item["aggregation"] or (metric.aggregation if metric else "soma"),
                "description": item["description"], "rule": item["rule"],
                "explanation": item.get("explanation", ""), "importance": item.get("importance", ""),
                "origin": item.get("origin") or "winthor", "requires_system": item.get("requires_system", ""),
                "erp_metric": item["erp_metric"], "erp_target": item["erp_target"],
                "default_filters": item["default_filters"],
                "entities": list(metric.entities) if metric else [],
                "requer": item["requer"],
                "status": KpiTemplate.Status.PRONTO if metric else KpiTemplate.Status.PLANEJADO,
                "tags": item["tags"], "order": ordem, "is_active": True,
            }
            _, created = KpiTemplate.objects.update_or_create(erp="winthor", code=item["code"], defaults=campos)
            vistos.add(item["code"])
            criados += created
            atualizados += not created
        desativados = KpiTemplate.objects.filter(erp="winthor").exclude(code__in=vistos).update(is_active=False)
        self.stdout.write(f"KPIs WinThor: {criados} criados, {atualizados} atualizados, {desativados} desativados.")
