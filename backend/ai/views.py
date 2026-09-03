from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsRoot
from accounts.tenancy import TenantScopedViewSet, get_request_tenant

from .context import tenant_results_context
from .models import AIChatMessage, AIChatSession, AIInsight, AIIntegration
from .prompts import prompt_chat_system
from .providers.base import AIProviderError
from .providers.factory import PROVIDERS, get_provider
from .serializers import (
    AIChatMessageSerializer,
    AIChatSessionSerializer,
    AIInsightSerializer,
    AIIntegrationSerializer,
)
from .tasks import gerar_insight


class AIIntegrationView(APIView):
    permission_classes = [IsRoot]

    def get_object(self):
        return AIIntegration.objects.order_by("-is_active", "id").first()

    def get(self, request):
        integration = self.get_object()
        if integration is None:
            return Response(None)
        return Response(AIIntegrationSerializer(integration).data)

    def put(self, request):
        integration = self.get_object()
        serializer = AIIntegrationSerializer(integration, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AIIntegrationSerializer(serializer.instance).data)


class AIIntegrationTestView(APIView):
    permission_classes = [IsRoot]

    def post(self, request):
        integration = AIIntegration.objects.filter(is_active=True).first()
        if integration is None:
            return Response({"ok": False, "message": "Nenhuma integração configurada."})
        cls = PROVIDERS.get(integration.provider)
        ok, message = False, ""
        if cls is None:
            message = f"Provedor {integration.provider} ainda não suportado."
        else:
            try:
                result = cls(integration).chat(
                    [{"role": "user", "content": "Responda apenas: OK"}], max_tokens=10
                )
                ok, message = True, f"Conexão OK — resposta: {result.content.strip()[:50]}"
            except AIProviderError as exc:
                message = str(exc)
        integration.last_test_at = timezone.now()
        integration.last_test_ok = ok
        integration.save(update_fields=["last_test_at", "last_test_ok"])
        return Response({"ok": ok, "message": message})


class AIInsightViewSet(TenantScopedViewSet):
    queryset = AIInsight.objects.select_related("indicator", "requested_by")
    serializer_class = AIInsightSerializer
    filterset_fields = ["kind", "status", "indicator", "deviation"]
    pagination_class = None
    http_method_names = ["get", "post", "delete"]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        serializer = AIInsightSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        indicator = serializer.validated_data.get("indicator")
        deviation = serializer.validated_data.get("deviation")
        for obj in (indicator, deviation):
            if obj is not None and obj.tenant_id != tenant.id:
                raise ValidationError("Recurso de outra empresa.")

        # Sugestão de mapa trabalha sobre a empresa inteira; as demais análises
        # precisam de um indicador ou de um desvio como alvo.
        kind = serializer.validated_data.get("kind")
        if kind != AIInsight.Kind.SUGESTAO_MAPA and indicator is None and deviation is None:
            raise ValidationError("Informe o indicador ou o desvio a analisar.")

        insight = serializer.save(tenant=tenant, requested_by=request.user)
        gerar_insight.delay(insight.id)
        return Response(AIInsightSerializer(insight).data, status=201)


class AIChatSessionViewSet(TenantScopedViewSet):
    queryset = AIChatSession.objects.prefetch_related("messages")
    serializer_class = AIChatSessionSerializer
    pagination_class = None
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def perform_create(self, serializer):
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        serializer.save(tenant=tenant, user=self.request.user)

    @action(detail=True, methods=["post"])
    def messages(self, request, pk=None):
        session = self.get_object()
        content = (request.data.get("content") or "").strip()
        if not content:
            raise ValidationError({"content": "Mensagem vazia."})

        AIChatMessage.objects.create(
            session=session, role=AIChatMessage.Role.USER, content=content
        )
        if session.messages.count() <= 1:
            session.title = content[:80]
        session.save()

        context = tenant_results_context(session.tenant)
        history = [
            {"role": m.role, "content": m.content}
            for m in session.messages.exclude(role=AIChatMessage.Role.SYSTEM)
        ][-20:]
        messages = [{"role": "system", "content": prompt_chat_system(context)}] + history

        try:
            result = get_provider().chat(messages)
            reply = AIChatMessage.objects.create(
                session=session, role=AIChatMessage.Role.ASSISTANT, content=result.content
            )
            return Response(AIChatMessageSerializer(reply).data, status=201)
        except AIProviderError as exc:
            return Response({"detail": str(exc)}, status=502)
