import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def amostrar_servidor():
    """Guarda uma amostra de CPU, memória, disco, load e banco; mantém 30 dias."""
    from .models import ServerSample
    from .monitor import amostra_rapida

    ServerSample.objects.create(**amostra_rapida())
    ServerSample.objects.filter(at__lt=timezone.now() - timedelta(days=30)).delete()
    return 1
