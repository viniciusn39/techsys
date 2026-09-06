from django.conf import settings
from django.db import models

from accounts.models import OrgUnit, TenantOwnedModel


class StrategicMap(TenantOwnedModel):
    name = models.CharField("nome", max_length=200)
    year_start = models.PositiveIntegerField("ano inicial")
    year_end = models.PositiveIntegerField("ano final")
    purpose = models.TextField("propósito", blank=True)
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


# ============================================================================
# Diagnóstico e identidade: SWOT, Canvas, stakeholders e reuniões de gestão
# ============================================================================

class SwotItem(TenantOwnedModel):
    """Item da análise SWOT do mapa: força, fraqueza, oportunidade ou ameaça."""

    class Quadrant(models.TextChoices):
        FORCA = "S", "Força"
        FRAQUEZA = "W", "Fraqueza"
        OPORTUNIDADE = "O", "Oportunidade"
        AMEACA = "T", "Ameaça"

    map = models.ForeignKey(StrategicMap, on_delete=models.CASCADE, related_name="swot_items")
    quadrant = models.CharField(max_length=1, choices=Quadrant.choices)
    text = models.CharField("descrição", max_length=300)
    detail = models.TextField(blank=True)
    impact = models.PositiveSmallIntegerField("impacto (1–5)", default=3)
    objective = models.ForeignKey(
        StrategicObjective, on_delete=models.SET_NULL, null=True, blank=True, related_name="swot_items",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["quadrant", "-impact", "order", "id"]

    def __str__(self):
        return f"[{self.quadrant}] {self.text}"


class SwotStrategy(TenantOwnedModel):
    """Cruzamento da matriz SWOT: o que fazer com cada combinação de fatores."""

    class Kind(models.TextChoices):
        SO = "SO", "Forças × Oportunidades (ofensiva)"
        WO = "WO", "Fraquezas × Oportunidades (reforço)"
        ST = "ST", "Forças × Ameaças (defesa)"
        WT = "WT", "Fraquezas × Ameaças (sobrevivência)"

    map = models.ForeignKey(StrategicMap, on_delete=models.CASCADE, related_name="swot_strategies")
    kind = models.CharField(max_length=2, choices=Kind.choices)
    text = models.CharField("estratégia", max_length=300)
    objective = models.ForeignKey(
        StrategicObjective, on_delete=models.SET_NULL, null=True, blank=True, related_name="swot_strategies",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["kind", "order", "id"]

    def __str__(self):
        return f"[{self.kind}] {self.text}"


class CanvasItem(TenantOwnedModel):
    """Post-it de um bloco do Business Model Canvas do mapa."""

    class Block(models.TextChoices):
        PARCERIAS = "parcerias", "Parcerias principais"
        ATIVIDADES = "atividades", "Atividades principais"
        RECURSOS = "recursos", "Recursos principais"
        PROPOSTA = "proposta", "Proposta de valor"
        RELACIONAMENTO = "relacionamento", "Relacionamento com clientes"
        CANAIS = "canais", "Canais"
        SEGMENTOS = "segmentos", "Segmentos de clientes"
        CUSTOS = "custos", "Estrutura de custos"
        RECEITAS = "receitas", "Fontes de receita"

    map = models.ForeignKey(StrategicMap, on_delete=models.CASCADE, related_name="canvas_items")
    block = models.CharField(max_length=20, choices=Block.choices)
    text = models.CharField(max_length=300)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["block", "order", "id"]

    def __str__(self):
        return f"[{self.block}] {self.text}"


class Stakeholder(TenantOwnedModel):
    """Parte interessada no planejamento: sócio, consultor, gerente, fornecedor, cliente-chave."""

    class Kind(models.TextChoices):
        INTERNO = "interno", "Interno"
        EXTERNO = "externo", "Externo"

    name = models.CharField("nome", max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.INTERNO)
    organization = models.CharField("empresa/organização", max_length=150, blank=True)
    role = models.CharField("papel", max_length=120, blank=True)
    email = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    # Matriz poder × interesse (1–5): define quem gerenciar de perto, manter satisfeito, informado ou monitorar.
    influence = models.PositiveSmallIntegerField("influência", default=3)
    interest = models.PositiveSmallIntegerField("interesse", default=3)
    expectations = models.TextField("expectativas", blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="stakeholder_profiles",
    )
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="stakeholders")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def strategy(self):
        alto_poder, alto_interesse = self.influence >= 4, self.interest >= 4
        if alto_poder and alto_interesse:
            return "gerenciar de perto"
        if alto_poder:
            return "manter satisfeito"
        if alto_interesse:
            return "manter informado"
        return "monitorar"


class Meeting(TenantOwnedModel):
    """Ritual de gestão: reunião de resultados, de planejamento, de acompanhamento de planos."""

    class Kind(models.TextChoices):
        RESULTADOS = "resultados", "Reunião de resultados"
        PLANEJAMENTO = "planejamento", "Planejamento estratégico"
        ACOMPANHAMENTO = "acompanhamento", "Acompanhamento de planos"
        DIRETORIA = "diretoria", "Diretoria"
        OUTRA = "outra", "Outra"

    class Status(models.TextChoices):
        AGENDADA = "agendada", "Agendada"
        REALIZADA = "realizada", "Realizada"
        CANCELADA = "cancelada", "Cancelada"

    title = models.CharField("título", max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.RESULTADOS)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AGENDADA)
    starts_at = models.DateTimeField("início")
    ends_at = models.DateTimeField("fim", null=True, blank=True)
    location = models.CharField("local / link", max_length=200, blank=True)
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="meetings")
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="organized_meetings",
    )
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="meetings")
    stakeholders = models.ManyToManyField(Stakeholder, blank=True, related_name="meetings")
    agenda = models.TextField("pauta", blank=True)
    minutes = models.TextField("ata", blank=True)
    decisions = models.TextField("decisões", blank=True)
    # Indicadores revisados na reunião (reunião de resultados).
    indicators = models.ManyToManyField("indicators.Indicator", blank=True, related_name="meetings")

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return f"{self.title} ({self.starts_at:%d/%m/%Y})"
