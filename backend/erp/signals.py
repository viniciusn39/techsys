from django.db.models.signals import post_save
from django.dispatch import receiver

from indicators.models import DataSource

from .models import Connector


@receiver(post_save, sender=Connector)
def criar_fonte_de_dados(sender, instance, created, **kwargs):
    """Todo conector aparece como fonte de dados do tipo agente nos indicadores."""
    if created:
        DataSource.objects.get_or_create(
            tenant=instance.tenant,
            type=DataSource.Type.AGENT,
            name=f"{instance.get_erp_display()} — {instance.name}",
            defaults={"config": {"connector_id": instance.id}},
        )
