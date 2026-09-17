import os
import uuid
from datetime import date

from django.db import models

from accounts.models import TenantOwnedModel


def caminho(instance, filename):
    return f"faturas/{instance.tenant_id}/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()[:10]}"


class Invoice(TenantOwnedModel):
    """Fatura que a plataforma lança para a empresa cliente. Só o root lança; a empresa consulta e baixa."""

    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        PAGA = "paga", "Paga"
        CANCELADA = "cancelada", "Cancelada"

    number = models.CharField("número", max_length=40)
    description = models.CharField("descrição", max_length=250)
    reference = models.DateField("competência", help_text="Primeiro dia do mês de referência")
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    due_date = models.DateField("vencimento")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ABERTA)
    paid_at = models.DateField("pago em", null=True, blank=True)
    payment_url = models.URLField("link de pagamento", blank=True)
    file = models.FileField("PDF / boleto", upload_to=caminho, null=True, blank=True, max_length=200)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["-due_date", "-id"]
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_invoice_number")]

    def __str__(self):
        return f"{self.number} · {self.tenant_id}"

    @property
    def overdue(self):
        return self.status == self.Status.ABERTA and self.due_date < date.today()
