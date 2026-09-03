import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def recalcular_farois(tenant_id=None):
    """Recomputa atingimento/farol dos valores do ano corrente (pega mudanças de meta)."""
    from datetime import date

    from .models import Indicator
    from .services import recompute_indicator

    qs = Indicator.objects.filter(is_active=True)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    count = 0
    for indicator in qs:
        for value in indicator.values.filter(period__year=date.today().year):
            value.save()
            count += 1
    logger.info("recalcular_farois: %s valores recalculados", count)
    return count


@shared_task
def coletar_fontes_dados():
    """Coleta automática das fontes de dados não-manuais (gancho do agente ERP)."""
    from .models import DataSource
    from .sources.registry import get_source

    sources = DataSource.objects.filter(is_active=True).exclude(type=DataSource.Type.MANUAL)
    if not sources.exists():
        logger.info("coletar_fontes_dados: nenhuma fonte automática configurada")
        return 0
    collected = 0
    for ds in sources:
        source = get_source(ds)
        if source is None:
            logger.warning("Fonte %s (%s) sem implementação registrada", ds.name, ds.type)
            continue
        for indicator in ds.indicators.filter(is_active=True):
            # A implementação de coleta por período entra junto com o agente ERP.
            logger.info("Coleta pendente de implementação: %s", indicator.code)
    return collected
