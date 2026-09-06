from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.tenancy import get_request_tenant

from .models import Ticket, TicketMessage
from .serializers import TicketDetailSerializer, TicketMessageSerializer, TicketSerializer


def _e_root(user):
    return user.role == User.Role.ROOT


class TicketViewSet(viewsets.ModelViewSet):
    """Chamados. Cliente: os da sua empresa (colaborador só os próprios). Root: todos, com ?tenant=."""

    queryset = Ticket.objects.select_related("tenant", "opened_by", "assigned_to")
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        return TicketDetailSerializer if self.action == "retrieve" else TicketSerializer

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if _e_root(user):
            tenant = get_request_tenant(self.request)
            if tenant is not None:
                qs = qs.filter(tenant=tenant)
            elif self.request.query_params.get("tenant"):
                qs = qs.filter(tenant_id=self.request.query_params["tenant"])
        else:
            tenant = get_request_tenant(self.request)
            if tenant is None:
                return qs.none()
            qs = qs.filter(tenant=tenant)
            if user.role == User.Role.COLABORADOR:
                qs = qs.filter(opened_by=user)
        status_ = self.request.query_params.get("status")
        if status_ == "abertos":
            qs = qs.exclude(status__in=[Ticket.Status.RESOLVIDO, Ticket.Status.FECHADO])
        elif status_:
            qs = qs.filter(status=status_)
        if self.request.query_params.get("category"):
            qs = qs.filter(category=self.request.query_params["category"])
        return qs

    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request)
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        ticket = serializer.save(tenant=tenant, opened_by=self.request.user, status=Ticket.Status.ABERTO)
        TicketMessage.objects.create(ticket=ticket, author=self.request.user, body=ticket.description, from_support=_e_root(self.request.user))

    def perform_update(self, serializer):
        user = self.request.user
        antes = serializer.instance.status
        dados = serializer.validated_data
        # Cliente só mexe em título/descrição/prioridade/categoria/avaliação e pode fechar ou reabrir o próprio chamado.
        if not _e_root(user):
            permitidos = {"title", "description", "priority", "category", "module", "rating", "rating_comment", "status"}
            extras = set(dados) - permitidos
            if extras:
                raise PermissionDenied(f"Campo(s) só do suporte: {', '.join(sorted(extras))}.")
            if "status" in dados and dados["status"] not in (Ticket.Status.FECHADO, Ticket.Status.ABERTO):
                raise PermissionDenied("O cliente só pode fechar ou reabrir o chamado.")
        ticket = serializer.save()
        agora = timezone.now()
        if ticket.status != antes:
            if ticket.status == Ticket.Status.RESOLVIDO and not ticket.resolved_at:
                ticket.resolved_at = agora
            if ticket.status == Ticket.Status.FECHADO and not ticket.closed_at:
                ticket.closed_at = agora
            if ticket.status in (Ticket.Status.ABERTO, Ticket.Status.EM_ATENDIMENTO):
                ticket.resolved_at = None
                ticket.closed_at = None
            ticket.save(update_fields=["resolved_at", "closed_at"])
            TicketMessage.objects.create(
                ticket=ticket, author=user, from_support=_e_root(user),
                body=f"Situação alterada para: {ticket.get_status_display()}.",
            )

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        ticket = self.get_object()
        user = request.user
        if request.method == "GET":
            qs = ticket.messages.select_related("author")
            if not _e_root(user):
                qs = qs.filter(is_internal=False)
            return Response(TicketMessageSerializer(qs, many=True).data)
        body = (request.data.get("body") or "").strip()
        if not body:
            raise ValidationError({"body": "Escreva a mensagem."})
        interna = bool(request.data.get("is_internal")) and _e_root(user)
        msg = TicketMessage.objects.create(ticket=ticket, author=user, body=body, is_internal=interna, from_support=_e_root(user))
        campos = []
        if _e_root(user) and not interna:
            if ticket.first_response_at is None:
                ticket.first_response_at = timezone.now()
                campos.append("first_response_at")
            if ticket.status == Ticket.Status.ABERTO:
                ticket.status = Ticket.Status.EM_ATENDIMENTO
                campos.append("status")
            if ticket.assigned_to_id is None:
                ticket.assigned_to = user
                campos.append("assigned_to")
        elif not _e_root(user) and ticket.status == Ticket.Status.AGUARDANDO_CLIENTE:
            ticket.status = Ticket.Status.EM_ATENDIMENTO
            campos.append("status")
        if campos:
            ticket.save(update_fields=campos)
        return Response(TicketMessageSerializer(msg).data, status=201)

    @action(detail=False, methods=["get"])
    def resumo(self, request):
        qs = self.get_queryset()
        por_status = {k: 0 for k in Ticket.Status.values}
        for r in qs.values("status").annotate(n=Count("id")):
            por_status[r["status"]] = r["n"]
        abertos = qs.exclude(status__in=[Ticket.Status.RESOLVIDO, Ticket.Status.FECHADO])
        out = {
            "total": qs.count(), "abertos": abertos.count(), "por_status": por_status,
            "sem_resposta": abertos.filter(first_response_at__isnull=True).count(),
            "urgentes": abertos.filter(priority=Ticket.Priority.URGENTE).count(),
        }
        if _e_root(request.user):
            out["por_empresa"] = [
                {"tenant_id": r["tenant_id"], "tenant_name": r["tenant__name"], "abertos": r["n"]}
                for r in abertos.values("tenant_id", "tenant__name").annotate(n=Count("id")).order_by("-n")
            ]
            out["atendentes"] = [{"id": u.id, "name": u.get_full_name() or u.email} for u in User.objects.filter(role=User.Role.ROOT, is_active=True)]
        return Response(out)
