import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def detectar_desvios():
    """Garante desvio para todo valor vermelho sem desvio (rede de segurança do signal)."""
    from indicators.models import IndicatorValue

    from .models import Deviation

    created = 0
    reds = IndicatorValue.objects.filter(
        status=IndicatorValue.Status.VERMELHO, deviation__isnull=True
    ).select_related("indicator")
    for value in reds:
        Deviation.objects.get_or_create(
            indicator_value=value,
            defaults={"tenant": value.indicator.tenant, "indicator": value.indicator},
        )
        created += 1
    logger.info("detectar_desvios: %s desvios criados", created)
    return created


@shared_task
def marcar_planos_atrasados():
    """Loga planos vencidos (aparece no dashboard via query; aqui só telemetria/beat)."""
    from datetime import date

    from .models import ActionPlan

    overdue = ActionPlan.objects.filter(when_end__lt=date.today()).exclude(
        status__in=[ActionPlan.Status.CONCLUIDO, ActionPlan.Status.CANCELADO]
    )
    count = overdue.count()
    logger.info("marcar_planos_atrasados: %s planos atrasados", count)
    return count
