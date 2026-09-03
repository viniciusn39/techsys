from django.conf import settings
from django.db import models

from accounts.models import OrgUnit, TenantOwnedModel


class Deviation(TenantOwnedModel):
    class Status(models.TextChoices):
        ABERTO = "aberto", "Aberto"
        EM_TRATAMENTO = "em_tratamento", "Em tratamento"
        CONCLUIDO = "concluido", "Concluído"

    indicator = models.ForeignKey(
        "indicators.Indicator", on_delete=models.CASCADE, related_name="deviations"
    )
    indicator_value = models.OneToOneField(
        "indicators.IndicatorValue", on_delete=models.CASCADE, related_name="deviation"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABERTO)
    root_cause = models.TextField("análise de causa", blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"Desvio {self.indicator.code} {self.indicator_value.period:%m/%Y}"


class ActionPlan(TenantOwnedModel):
    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        CONCLUIDO = "concluido", "Concluído"
        CANCELADO = "cancelado", "Cancelado"

    class PdcaStage(models.TextChoices):
        PLAN = "plan", "Plan"
        DO = "do", "Do"
        CHECK = "check", "Check"
        ACT = "act", "Act"

    class Origin(models.TextChoices):
        MANUAL = "manual", "Manual"
        DESVIO = "desvio", "Desvio"

    class Priority(models.TextChoices):
        BAIXA = "baixa", "Baixa"
        MEDIA = "media", "Média"
        ALTA = "alta", "Alta"

    title = models.CharField("título", max_length=250)
    what = models.TextField("o quê", blank=True)
    why = models.TextField("por quê", blank=True)
    where = models.CharField("onde", max_length=250, blank=True)
    who = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="action_plans", verbose_name="quem",
    )
    when_start = models.DateField("início", null=True, blank=True)
    when_end = models.DateField("fim", null=True, blank=True)
    how = models.TextField("como", blank=True)
    how_much = models.DecimalField(
        "quanto custa", max_digits=14, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO)
    pdca_stage = models.CharField(max_length=10, choices=PdcaStage.choices, default=PdcaStage.PLAN)
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.MANUAL)
    deviation = models.ForeignKey(
        Deviation, on_delete=models.SET_NULL, null=True, blank=True, related_name="action_plans"
    )
    objective = models.ForeignKey(
        "strategy.StrategicObjective", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="action_plans",
    )
    indicator = models.ForeignKey(
        "indicators.Indicator", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="action_plans",
    )
    org_unit = models.ForeignKey(
        OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="action_plans"
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIA)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class ActionItem(models.Model):
    class Status(models.TextChoices):
        A_FAZER = "a_fazer", "A fazer"
        FAZENDO = "fazendo", "Fazendo"
        FEITO = "feito", "Feito"

    plan = models.ForeignKey(ActionPlan, on_delete=models.CASCADE, related_name="items")
    title = models.CharField("título", max_length=250)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="action_items",
    )
    due_date = models.DateField("prazo", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.A_FAZER)
    order = models.PositiveIntegerField(default=0)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title
