from django.conf import settings
from django.db import models

from accounts.models import OrgUnit, TenantOwnedModel


class StrategicMap(TenantOwnedModel):
    name = models.CharField("nome", max_length=200)
    year_start = models.PositiveIntegerField("ano inicial")
    year_end = models.PositiveIntegerField("ano final")
    mission = models.TextField("missão", blank=True)
    vision = models.TextField("visão", blank=True)
    values_text = models.TextField("valores", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-year_start"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            StrategicMap.objects.filter(tenant=self.tenant, is_active=True).exclude(
                pk=self.pk
            ).update(is_active=False)


class Perspective(models.Model):
    map = models.ForeignKey(StrategicMap, on_delete=models.CASCADE, related_name="perspectives")
    name = models.CharField("nome", max_length=100)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=7, default="#0d6efd")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class StrategicObjective(TenantOwnedModel):
    perspective = models.ForeignKey(
        Perspective, on_delete=models.CASCADE, related_name="objectives"
    )
    name = models.CharField("nome", max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="objectives",
    )
    order = models.PositiveIntegerField(default=0)
    # Relação de causa e efeito do BSC: "este objetivo contribui para aquele".
    contributes_to = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="contributed_by"
    )
    # Posição no diagrama, em % da largura da faixa (0–100). Nulo = auto-layout.
    pos_x = models.FloatField(null=True, blank=True)
    pos_y = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class Goal(TenantOwnedModel):
    class Level(models.TextChoices):
        EMPRESA = "empresa", "Empresa"
        AREA = "area", "Área"
        TIME = "time", "Time"
        PESSOA = "pessoa", "Pessoa"

    class Status(models.TextChoices):
        ATIVO = "ativo", "Ativo"
        CONCLUIDO = "concluido", "Concluído"
        CANCELADO = "cancelado", "Cancelado"

    objective = models.ForeignKey(
        StrategicObjective, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="goals",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.EMPRESA)
    org_unit = models.ForeignKey(
        OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="goals"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="goals"
    )
    name = models.CharField("nome", max_length=250)
    description = models.TextField(blank=True)
    indicator = models.ForeignKey(
        "indicators.Indicator", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="goals",
    )
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ATIVO)

    class Meta:
        ordering = ["level", "name"]

    def __str__(self):
        return self.name
