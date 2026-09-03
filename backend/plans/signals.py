from django.db.models.signals import post_save
from django.dispatch import receiver

from indicators.models import IndicatorValue

from .models import Deviation


@receiver(post_save, sender=IndicatorValue)
def criar_desvio_para_valor_vermelho(sender, instance, **kwargs):
    if instance.status == IndicatorValue.Status.VERMELHO:
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
