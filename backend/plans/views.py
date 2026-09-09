from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.permissions import IsGestorOrAbove
from accounts.tenancy import TenantScopedViewSet, get_request_tenant

from .models import ActionItem, ActionPlan, ActionPlanUpdate, Deviation
from .serializers import ActionItemSerializer, ActionPlanSerializer, ActionPlanUpdateSerializer, DeviationSerializer

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

    @action(detail=True, methods=["get"])
    def guia(self, request, pk=None):
        """Apoio ao tratamento: o que o indicador mede, impacto do desvio, causas
        comuns, dicas de ação e o tamanho do gap frente à meta."""
        from erp.guia_desvios import guia_desvio

        return Response(guia_desvio(self.get_object()))

    @action(detail=True, methods=["post"], url_path="create-plan")
    def create_plan(self, request, pk=None):
        """Plano 5W2H já preenchido a partir do desvio: título, o quê, por quê, prazo,
        prioridade pela gravidade, objetivo do indicador e um checklist inicial."""
        from calendar import monthrange
        from datetime import date

        deviation = self.get_object()
        value = deviation.indicator_value
        indicator = deviation.indicator
        meta = indicator.targets.filter(period=value.period).first()
        dec = int(indicator.decimals or 0)
        fmt = lambda v: f"{float(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
        pct = float(value.achievement_pct or 0)
        hoje = date.today()
        prox = (hoje.replace(day=28) + __import__("datetime").timedelta(days=4)).replace(day=1)
        fim = prox.replace(day=monthrange(prox.year, prox.month)[1])
        alvo = f" para {fmt(meta.target_value)} {indicator.unit}" if meta else ""
        plan = ActionPlan.objects.create(
            tenant=deviation.tenant,
            title=f"Recuperar {indicator.name} ({value.period:%m/%Y}): {fmt(value.value)} {indicator.unit}{' → ' + fmt(meta.target_value) + ' ' + indicator.unit if meta else ''}".strip(),
            what=f"Levar {indicator.code} · {indicator.name} de {fmt(value.value)} {indicator.unit}{alvo} "
                 f"(hoje {pct:.1f}% da meta de {value.period:%m/%Y}).",
            why=deviation.root_cause or f"Farol vermelho em {value.period:%m/%Y}: {pct:.1f}% da meta. Causa raiz a registrar no desvio.",
            where=indicator.org_unit.name if indicator.org_unit else "",
            how="1) Confirmar a causa raiz com a equipe. 2) Definir as contramedidas e os responsáveis. 3) Acompanhar semanalmente no Kanban e na reunião de resultados.",
            who=request.user,
            when_start=hoje,
            when_end=fim,
            status=ActionPlan.Status.EM_ANDAMENTO,
            origin=ActionPlan.Origin.DESVIO,
            deviation=deviation,
            indicator=indicator,
            objective=indicator.objective,
            org_unit=indicator.org_unit,
            priority=ActionPlan.Priority.ALTA if pct < 70 else ActionPlan.Priority.MEDIA,
        )
        for ordem, (titulo, dias, prio) in enumerate([
            ("Levantar a causa raiz com a equipe (5 porquês)", 5, ActionItem.Priority.ALTA),
            ("Definir contramedidas e responsáveis", 10, ActionItem.Priority.ALTA),
            (f"Acompanhar {indicator.code} na próxima reunião de resultados", 30, ActionItem.Priority.MEDIA),
        ]):
            ActionItem.objects.create(plan=plan, title=titulo, order=ordem, priority=prio, responsible=request.user,
                                      due_date=hoje + __import__("datetime").timedelta(days=dias))
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

    @action(detail=True, methods=["get", "post"])
    def updates(self, request, pk=None):
        """Registro de acompanhamento do plano (linha do tempo)."""
        plan = self.get_object()
        if request.method == "GET":
            return Response(ActionPlanUpdateSerializer(plan.updates.select_related("author"), many=True).data)
        ser = ActionPlanUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        upd = ser.save(plan=plan, author=request.user)
        if plan.status == ActionPlan.Status.RASCUNHO:
            plan.status = ActionPlan.Status.EM_ANDAMENTO
            plan.save(update_fields=["status"])
        return Response(ActionPlanUpdateSerializer(upd).data, status=201)

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
        if new_status in (ActionItem.Status.FAZENDO, ActionItem.Status.FEITO) and item.started_at is None:
            item.started_at = timezone.now()
        if new_status != ActionItem.Status.BLOQUEADO:
            item.blocked_reason = ""
        item.save()

    @action(detail=False, methods=["get"])
    def analise(self, request):
        """Números do quadro: por status, por responsável, atrasadas, lead time e vazão semanal."""
        from collections import Counter, defaultdict
        from datetime import date, timedelta

        hoje = date.today()
        itens = list(self.get_queryset().exclude(plan__status=ActionPlan.Status.CANCELADO))
        abertos = [i for i in itens if i.status != ActionItem.Status.FEITO]
        atrasadas = [i for i in abertos if i.due_date and i.due_date < hoje]
        por_status = Counter(i.status for i in itens)
        por_resp = defaultdict(lambda: {"abertas": 0, "feitas": 0, "atrasadas": 0, "bloqueadas": 0})
        for i in itens:
            nome = i.responsible.first_name if i.responsible else "(sem responsável)"
            r = por_resp[nome]
            if i.status == ActionItem.Status.FEITO:
                r["feitas"] += 1
            else:
                r["abertas"] += 1
                if i.due_date and i.due_date < hoje:
                    r["atrasadas"] += 1
                if i.status == ActionItem.Status.BLOQUEADO:
                    r["bloqueadas"] += 1
        leads = [(i.done_at - i.started_at).total_seconds() / 86400 for i in itens if i.done_at and i.started_at and i.done_at >= i.started_at]
        semanas = []
        seg = hoje - timedelta(days=hoje.weekday())
        for k in range(7, -1, -1):
            ini = seg - timedelta(weeks=k)
            fim = ini + timedelta(days=6)
            semanas.append({
                "semana": ini.isoformat(),
                "feitas": sum(1 for i in itens if i.done_at and ini <= i.done_at.date() <= fim),
                "criadas": sum(1 for i in itens if i.created_at and ini <= i.created_at.date() <= fim),
            })
        return Response({
            "total": len(itens), "abertas": len(abertos), "atrasadas": len(atrasadas),
            "por_status": {k: por_status.get(k, 0) for k in ActionItem.Status.values},
            "por_responsavel": [{"nome": n, **v} for n, v in sorted(por_resp.items(), key=lambda kv: -kv[1]["abertas"])],
            "lead_time_medio_dias": round(sum(leads) / len(leads), 1) if leads else None,
            "concluidas_30d": sum(1 for i in itens if i.done_at and i.done_at.date() >= hoje - timedelta(days=30)),
            "semanas": semanas,
        })

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
