"""Chamados: o cliente abre para o suporte ou para a consultoria; o root (TechSys) atende.

Um chamado pertence à empresa (tenant) e tem uma conversa (mensagens). Notas
internas são visíveis só para o root. Ao resolver, o cliente pode avaliar.
"""
from django.conf import settings
from django.db import models

from accounts.models import TenantOwnedModel


class Ticket(TenantOwnedModel):
    class Category(models.TextChoices):
        SUPORTE = "suporte", "Suporte técnico"
        CONSULTORIA = "consultoria", "Consultoria de gestão"
        DUVIDA = "duvida", "Dúvida de uso"
        ERRO = "erro", "Erro no sistema"
        MELHORIA = "melhoria", "Sugestão de melhoria"
        DADOS = "dados", "Dados do ERP / indicador"

    class Priority(models.TextChoices):
        BAIXA = "baixa", "Baixa"
        MEDIA = "media", "Média"
        ALTA = "alta", "Alta"
        URGENTE = "urgente", "Urgente"

    class Status(models.TextChoices):
        ABERTO = "aberto", "Aberto"
        EM_ATENDIMENTO = "em_atendimento", "Em atendimento"
        AGUARDANDO_CLIENTE = "aguardando_cliente", "Aguardando cliente"
        RESOLVIDO = "resolvido", "Resolvido"
        FECHADO = "fechado", "Fechado"

    number = models.PositiveIntegerField("número", db_index=True)
    title = models.CharField("título", max_length=200)
    description = models.TextField("descrição")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SUPORTE)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIA)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABERTO)
    module = models.CharField("módulo", max_length=40, blank=True)       # chave do menu, opcional
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="tickets_opened")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets_assigned")
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    rating = models.PositiveSmallIntegerField("avaliação (1–5)", null=True, blank=True)
    rating_comment = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_ticket_number_tenant")]

    def __str__(self):
        return f"#{self.number} {self.title}"

    @property
    def is_open(self):
        return self.status not in (self.Status.RESOLVIDO, self.Status.FECHADO)

    def save(self, *args, **kwargs):
        if not self.number:
            ultimo = Ticket.objects.filter(tenant=self.tenant).aggregate(m=models.Max("number"))["m"] or 0
            self.number = ultimo + 1
        super().save(*args, **kwargs)


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ticket_messages")
    body = models.TextField()
    is_internal = models.BooleanField("nota interna (só suporte)", default=False)
    from_support = models.BooleanField("resposta do suporte", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.ticket_id}: {self.body[:40]}"


class ServerSample(models.Model):
    """Amostra do servidor da plataforma (a cada 5 min) para o histórico da tela do root."""

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    cpu_pct = models.FloatField(null=True)
    mem_pct = models.FloatField(null=True)
    mem_usada = models.BigIntegerField(null=True)
    disco_pct = models.FloatField(null=True)
    disco_usado = models.BigIntegerField(null=True)
    load_m1 = models.FloatField(null=True)
    db_bytes = models.BigIntegerField(null=True)
    db_conexoes = models.IntegerField(null=True)

    class Meta:
        ordering = ["-at"]
