import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

from accounts.models import TenantOwnedModel


def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


class AIIntegration(models.Model):
    class Provider(models.TextChoices):
        DEEPSEEK = "deepseek", "DeepSeek"
        OPENAI = "openai", "OpenAI"

    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.DEEPSEEK)
    base_url = models.URLField(default="https://api.deepseek.com/v1")
    api_key_encrypted = models.TextField(blank=True)
    model = models.CharField(max_length=100, default="deepseek-chat")
    temperature = models.DecimalField(max_digits=3, decimal_places=1, default=0.3)
    max_tokens = models.PositiveIntegerField(default=2000)
    is_active = models.BooleanField(default=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_ok = models.BooleanField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.provider} ({self.model})"

    def set_api_key(self, raw_key):
        self.api_key_encrypted = _fernet().encrypt(raw_key.encode()).decode()

    def get_api_key(self):
        if not self.api_key_encrypted:
            return None
        try:
            return _fernet().decrypt(self.api_key_encrypted.encode()).decode()
        except InvalidToken:
            return None

    @property
    def api_key_set(self):
        return bool(self.api_key_encrypted)


class AIInsight(TenantOwnedModel):
    class Kind(models.TextChoices):
        ANALISE_INDICADOR = "analise_indicador", "Análise de indicador"
        ANALISE_DESVIO = "analise_desvio", "Análise de desvio"
        RESUMO_MENSAL = "resumo_mensal", "Resumo mensal"
        SUGESTAO_MAPA = "sugestao_mapa", "Sugestão de mapa estratégico"

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PROCESSANDO = "processando", "Processando"
        CONCLUIDO = "concluido", "Concluído"
        ERRO = "erro", "Erro"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    indicator = models.ForeignKey(
        "indicators.Indicator", on_delete=models.CASCADE, null=True, blank=True,
        related_name="insights",
    )
    deviation = models.ForeignKey(
        "plans.Deviation", on_delete=models.CASCADE, null=True, blank=True,
        related_name="insights",
    )
    period = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    content = models.TextField(blank=True)
    # Resultado estruturado, quando a análise devolve dados em vez de texto
    # (é o caso da sugestão de mapa: objetivos e ligações).
    data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ai_insights"
    )
    tokens_used = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]


class AIChatSession(TenantOwnedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_chat_sessions"
    )
    title = models.CharField(max_length=200, default="Nova conversa")

    class Meta:
        ordering = ["-updated_at"]


class AIChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Usuário"
        ASSISTANT = "assistant", "Assistente"
        SYSTEM = "system", "Sistema"

    session = models.ForeignKey(AIChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
