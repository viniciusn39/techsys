from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.permissions import IsGestorOrAbove
from accounts.tenancy import TenantScopedViewSet, get_request_tenant

from .models import ActionItem, ActionPlan, Deviation
from .serializers import ActionItemSerializer, ActionPlanSerializer, DeviationSerializer

PDCA_SEQUENCE = [
    ActionPlan.PdcaStage.PLAN,
    ActionPlan.PdcaStage.DO,
    ActionPlan.PdcaStage.CHECK,
    ActionPlan.PdcaStage.ACT,
]


def close_deviation_if_done(plan):
    """Plano concluído fecha o desvio de origem (se todos os planos dele concluíram)."""
    deviation = plan.deviation
    if deviation is None:
        return
    open_plans = deviation.action_plans.exclude(
        status__in=[ActionPlan.Status.CONCLUIDO, ActionPlan.Status.CANCELADO]
    )
    if plan.status == ActionPlan.Status.CONCLUIDO and not open_plans.exists():
        deviation.status = Deviation.Status.CONCLUIDO
        deviation.save(update_fields=["status"])


class DeviationViewSet(TenantScopedViewSet):
    queryset = Deviation.objects.select_related("indicator", "indicator_value")
    serializer_class = DeviationSerializer
    permission_classes = [IsGestorOrAbove]
    filterset_fields = ["status", "indicator"]
    pagination_class = None
    http_method_names = ["get", "patch", "post", "delete"]

    @action(detail=True, methods=["post"], url_path="create-plan")
    def create_plan(self, request, pk=None):
        deviation = self.get_object()
        value = deviation.indicator_value
        indicator = deviation.indicator
        plan = ActionPlan.objects.create(
            tenant=deviation.tenant,
            title=f"Tratar desvio: {indicator.name} ({value.period:%m/%Y})",
            what=f"Recuperar o indicador {indicator.code} - {indicator.name}, "
                 f"que atingiu {value.achievement_pct or 0}% da meta em {value.period:%m/%Y}.",
            why=deviation.root_cause or "Meta não atingida (farol vermelho).",
            who=request.user,
            status=ActionPlan.Status.EM_ANDAMENTO,
            origin=ActionPlan.Origin.DESVIO,
            deviation=deviation,
            indicator=indicator,
            org_unit=indicator.org_unit,
            priority=ActionPlan.Priority.ALTA,
        )
        if deviation.status == Deviation.Status.ABERTO:
            deviation.status = Deviation.Status.EM_TRATAMENTO
            deviation.save(update_fields=["status"])
        return Response(ActionPlanSerializer(plan).data, status=201)


class ActionPlanViewSet(TenantScopedViewSet):
    queryset = ActionPlan.objects.select_related(
        "who", "org_unit", "indicator", "deviation"
    ).prefetch_related("items")
    serializer_class = ActionPlanSerializer
    permission_classes = [IsGestorOrAbove]
    filterset_fields = ["status", "origin", "who", "org_unit", "pdca_stage", "priority"]
    search_fields = ["title", "what"]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    def perform_update(self, serializer):
        serializer.save()
        close_deviation_if_done(serializer.instance)

    @action(detail=True, methods=["post"], url_path="advance-pdca")
    def advance_pdca(self, request, pk=None):
        plan = self.get_object()
        idx = PDCA_SEQUENCE.index(plan.pdca_stage)
        if idx < len(PDCA_SEQUENCE) - 1:
            plan.pdca_stage = PDCA_SEQUENCE[idx + 1]
            plan.save(update_fields=["pdca_stage"])
        return Response(ActionPlanSerializer(plan, context=self.get_serializer_context()).data)


class ActionItemViewSet(viewsets.ModelViewSet):
    queryset = ActionItem.objects.select_related("plan", "responsible")
    serializer_class = ActionItemSerializer
    permission_classes = [IsGestorOrAbove]
    filterset_fields = ["plan", "status"]
    pagination_class = None

    def get_queryset(self):
        tenant = get_request_tenant(self.request)
        if tenant is None:
            return self.queryset.none()
        return self.queryset.filter(plan__tenant=tenant)

    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request)
        if tenant is None or serializer.validated_data["plan"].tenant_id != tenant.id:
            raise PermissionDenied("Plano de outra empresa.")
        serializer.save()

    def _apply_status(self, item, new_status):
        item.status = new_status
        item.done_at = timezone.now() if new_status == ActionItem.Status.FEITO else None
        item.save()

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        serializer.save()
        item = serializer.instance
        if item.status != old_status:
            self._apply_status(item, item.status)

    @action(detail=True, methods=["patch"])
    def move(self, request, pk=None):
        item = self.get_object()
        new_status = request.data.get("status")
        if new_status not in ActionItem.Status.values:
            raise ValidationError({"status": "Status inválido."})
        self._apply_status(item, new_status)
        if "order" in request.data:
            item.order = int(request.data["order"])
            item.save(update_fields=["order"])
        return Response(ActionItemSerializer(item).data)
