from django.conf import settings
from django.db import models

from accounts.models import TenantOwnedModel


class Board(TenantOwnedModel):
    """Quadro de tarefas (um sprint, um cliente, uma frente). Pode pertencer a um planejamento."""

    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    map = models.ForeignKey(
        "strategy.StrategicMap", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="boards", verbose_name="planejamento",
    )
    start_date = models.DateField("início", null=True, blank=True)
    end_date = models.DateField("fim", null=True, blank=True)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self):
        return self.name


class Task(models.Model):
    class Status(models.TextChoices):
        A_FAZER = "a_fazer", "A fazer"
        EM_PROGRESSO = "em_progresso", "Em progresso"
        BLOQUEADO = "bloqueado", "Bloqueado"
        CONCLUIDO = "concluido", "Concluído"

    class Priority(models.TextChoices):
        BAIXA = "baixa", "Baixa"
        MEDIA = "media", "Média"
        ALTA = "alta", "Alta"

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField("título", max_length=250)
    description = models.TextField("descrição", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.A_FAZER)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIA)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="kanban_tasks",
    )
    # Quem acompanha a tarefa: enxerga e participa da comunicação dela.
    watchers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="kanban_watching")
    due_date = models.DateField("prazo", null=True, blank=True)
    # [{"text": "...", "done": false}] — lista curta, sempre lida e gravada inteira com a tarefa.
    checklist = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="kanban_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class TaskEvent(models.Model):
    """Histórico da tarefa: criação, mudança de coluna, de responsável, de prazo."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="events")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    text = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class TaskMessage(models.Model):
    """Comunicação da tarefa: um pedido de alguém para alguém, que só fecha quando quem pediu confirma."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"                          # esperando a resposta do destinatário
        AGUARDANDO = "aguardando", "Aguardando confirmação"        # respondida; quem pediu ainda não confirmou
        CONCLUIDA = "concluida", "Concluída"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="kanban_sent")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="kanban_received")
    text = models.TextField("mensagem")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDENTE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]


class TaskReply(models.Model):
    message = models.ForeignKey(TaskMessage, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
