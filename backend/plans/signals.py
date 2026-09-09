from django.db.models.signals import post_save
from django.dispatch import receiver

from indicators.models import IndicatorValue

from .models import Deviation


def periodo_recente(period):
    """Desvio só nasce para o mês corrente ou o anterior: recalcular metas de um
    ano inteiro não pode abrir dezenas de desvios de meses já encerrados."""
    from datetime import date

    hoje = date.today()
    limite = (hoje.replace(day=1).replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=1)
    return period >= limite


@receiver(post_save, sender=IndicatorValue)
def criar_desvio_para_valor_vermelho(sender, instance, **kwargs):
    if instance.status == IndicatorValue.Status.VERMELHO and periodo_recente(instance.period):
        Deviation.objects.get_or_create(
            indicator_value=instance,
            defaults={
                "tenant": instance.indicator.tenant,
                "indicator": instance.indicator,
            },
        )
    else:
        # Valor corrigido/re-lançado deixou de ser vermelho: remove desvio ainda aberto.
        Deviation.objects.filter(
            indicator_value=instance, status=Deviation.Status.ABERTO
        ).delete()
