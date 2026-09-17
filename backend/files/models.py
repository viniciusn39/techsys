import os
import uuid

from django.conf import settings
from django.db import models

from accounts.models import TenantOwnedModel


def caminho(instance, filename):
    # Nome no disco não vem do usuário: pasta da empresa + uuid, só a extensão é aproveitada.
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"anexos/{instance.tenant_id}/{uuid.uuid4().hex}{ext}"


class Attachment(TenantOwnedModel):
    """Arquivo anexado a um registro (atividade de projeto, tarefa do kanban…).

    O alvo é (kind, object_id); quem resolve e confere se o alvo é da empresa é files.targets.
    O arquivo nunca é servido como estático: só pelo endpoint de download, autenticado.
    """

    kind = models.CharField(max_length=30)
    object_id = models.PositiveBigIntegerField()
    file = models.FileField(upload_to=caminho, max_length=200)
    name = models.CharField("nome original", max_length=200)
    size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tenant", "kind", "object_id"])]

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        arquivo = self.file
        super().delete(*args, **kwargs)
        if arquivo:
            arquivo.delete(save=False)
