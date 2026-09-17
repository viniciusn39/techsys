from django.conf import settings
from django.db import models

from accounts.models import OrgUnit, TenantOwnedModel


class Andamento(models.TextChoices):
    """Situação comum a projeto e atividade."""

    NAO_INICIADO = "nao_iniciado", "Não iniciado"
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    FINALIZADO = "finalizado", "Finalizado"
    PAUSADO = "pausado", "Pausado"
    CANCELADO = "cancelado", "Cancelado"


class Project(TenantOwnedModel):
    """Projeto estratégico: nasce do planejamento (mapa) e aponta para os itens da
    SWOT que ele trata e para os objetivos do mapa que ele faz avançar."""

    code = models.PositiveIntegerField("código")   # sequencial por empresa
    map = models.ForeignKey(
        "strategy.StrategicMap", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="projects", verbose_name="planejamento",
    )
    title = models.CharField("título", max_length=250)
    description = models.TextField("descrição", blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="projects_owned", verbose_name="responsável",
    )
    org_unit = models.ForeignKey(
        OrgUnit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="projects", verbose_name="departamento",
    )
    start_date = models.DateField("início")
    end_date = models.DateField("fim")
    status = models.CharField(max_length=20, choices=Andamento.choices, default=Andamento.NAO_INICIADO)
    partners = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="projects_partner", verbose_name="parceiros",
    )
    swot_items = models.ManyToManyField("strategy.SwotItem", blank=True, related_name="projects")
    objectives = models.ManyToManyField("strategy.StrategicObjective", blank=True, related_name="projects")

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_project_code")]

    def __str__(self):
        return f"{self.code} · {self.title}"


class ProjectActivity(models.Model):
    """Atividade da EAP do projeto. A árvore não tem limite de níveis; o avanço de
    quem tem filhas é a média delas (ver projects.services.calcular_arvore)."""

    class Phase(models.TextChoices):
        INICIACAO = "iniciacao", "Iniciação"
        PLANEJAMENTO = "planejamento", "Planejamento"
        EXECUCAO = "execucao", "Execução"
        MONITORAMENTO = "monitoramento", "Monitoramento"
        ENCERRAMENTO = "encerramento", "Encerramento"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="activities")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")
    title = models.CharField("nome", max_length=250)
    description = models.TextField("descrição", blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="project_activities",
    )
    phase = models.CharField("fase", max_length=20, choices=Phase.choices, default=Phase.INICIACAO)
    start_date = models.DateField("início", null=True, blank=True)
    end_date = models.DateField("fim", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Andamento.choices, default=Andamento.NAO_INICIADO)
    progress_pct = models.PositiveSmallIntegerField("% andamento", default=0)
    notes = models.TextField("registros", blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class ActivityFca(models.Model):
    """Fato · Causa · Ação: o tratamento de um problema encontrado numa atividade."""

    class Status(models.TextChoices):
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        CONCLUIDO = "concluido", "Concluído"
        CANCELADO = "cancelado", "Cancelado"

    activity = models.ForeignKey(ProjectActivity, on_delete=models.CASCADE, related_name="fcas")
    fact = models.TextField("fato")
    cause = models.TextField("causa", blank=True)
    action = models.TextField("ação", blank=True)
    due_date = models.DateField("prazo", null=True, blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="project_fcas",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EM_ANDAMENTO)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "id"]

    def __str__(self):
        return self.fact[:60]
