from django.conf import settings
from django.db import models

from accounts.models import OrgUnit, TenantOwnedModel


class DataSource(TenantOwnedModel):
    class Type(models.TextChoices):
        MANUAL = "manual", "Manual"
        API = "api", "API REST"
        SQL = "sql", "SQL"
        AGENT = "agent", "Agente ERP"

    name = models.CharField("nome", max_length=200)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.MANUAL)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Indicator(TenantOwnedModel):
    class Frequency(models.TextChoices):
        MENSAL = "mensal", "Mensal"
        TRIMESTRAL = "trimestral", "Trimestral"
        ANUAL = "anual", "Anual"

    class Polarity(models.TextChoices):
        MAIOR_MELHOR = "maior_melhor", "Maior é melhor"
        MENOR_MELHOR = "menor_melhor", "Menor é melhor"

    class Aggregation(models.TextChoices):
        SOMA = "soma", "Soma"
        MEDIA = "media", "Média"
        ULTIMO = "ultimo", "Último valor"

    code = models.CharField("código", max_length=30)
    name = models.CharField("nome", max_length=200)
    description = models.TextField(blank=True)
    unit = models.CharField("unidade", max_length=20, blank=True)
    decimals = models.PositiveSmallIntegerField(default=2)
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MENSAL)
    polarity = models.CharField(max_length=20, choices=Polarity.choices, default=Polarity.MAIOR_MELHOR)
    aggregation = models.CharField(max_length=20, choices=Aggregation.choices, default=Aggregation.SOMA)
    org_unit = models.ForeignKey(
        OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="indicators"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="indicators",
    )
    objective = models.ForeignKey(
        "strategy.StrategicObjective", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="indicators",
    )
    data_source = models.ForeignKey(
        DataSource, on_delete=models.SET_NULL, null=True, blank=True, related_name="indicators"
    )
    # Vínculo com o ERP: chave do catálogo erp.metrics. Preenchido = o valor
    # mensal é calculado do espelho do ERP (source=agent), não lançado à mão.
    erp_metric = models.CharField("métrica do ERP", max_length=60, blank=True, db_index=True)
    # Filtros da métrica, ex.: {"branch": "1"} (código da filial no ERP).
    erp_filters = models.JSONField(default=dict, blank=True)
    yellow_threshold_pct = models.DecimalField(max_digits=5, decimal_places=2, default=90)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_indicator_code_tenant")
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class IndicatorTarget(models.Model):
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name="targets")
    period = models.DateField("período")
    target_value = models.DecimalField("meta", max_digits=18, decimal_places=4)

    class Meta:
        ordering = ["period"]
        constraints = [
            models.UniqueConstraint(fields=["indicator", "period"], name="uniq_target_period")
        ]


class IndicatorValue(models.Model):
    class Status(models.TextChoices):
        VERDE = "verde", "Verde"
        AMARELO = "amarelo", "Amarelo"
        VERMELHO = "vermelho", "Vermelho"
        SEM_META = "sem_meta", "Sem meta"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        API = "api", "API"
        SQL = "sql", "SQL"
        AGENT = "agent", "Agente"

    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name="values")
    period = models.DateField("período")
    value = models.DecimalField("valor", max_digits=18, decimal_places=4)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="entered_values",
    )
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    note = models.TextField("observação", blank=True)
    achievement_pct = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SEM_META)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["period"]
        constraints = [
            models.UniqueConstraint(fields=["indicator", "period"], name="uniq_value_period")
        ]

    def save(self, *args, **kwargs):
        from .services import compute_achievement

        target = self.indicator.targets.filter(period=self.period).first()
        self.achievement_pct, self.status = compute_achievement(
            self.indicator, self.value, target.target_value if target else None
        )
        super().save(*args, **kwargs)
