from collections import Counter, defaultdict
from datetime import date

from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsGestorOrAbove, role_at_least
from accounts.tenancy import TenantScopedViewSet, get_request_tenant

from .models import Board, Task, TaskEvent, TaskMessage, TaskReply
from .serializers import BoardSerializer, TaskEventSerializer, TaskMessageSerializer, TaskSerializer, nome

ROTULO_STATUS = dict(Task.Status.choices)


class BoardViewSet(TenantScopedViewSet):
    queryset = Board.objects.select_related("map")
    serializer_class = BoardSerializer
    permission_classes = [IsGestorOrAbove]
    filterset_fields = ["map", "is_active"]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx


class _DoTenant(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = None
    tenant_path = "board__tenant"

    def tenant(self):
        return get_request_tenant(self.request)

    def get_queryset(self):
        tenant = self.tenant()
        if tenant is None:
            return self.queryset.none()
        return self.queryset.filter(**{self.tenant_path: tenant})

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.tenant()
        return ctx


class TaskViewSet(_DoTenant):
    queryset = Task.objects.select_related("board", "responsible").prefetch_related("watchers", "messages")
    serializer_class = TaskSerializer
    filterset_fields = ["board", "status", "priority", "responsible"]
    search_fields = ["title", "description"]

    def _evento(self, task, texto):
        TaskEvent.objects.create(task=task, author=self.request.user, text=texto[:300])

    def _aplicar_status(self, task, antigo):
        if task.status == antigo:
            return
        agora = timezone.now()
        task.done_at = agora if task.status == Task.Status.CONCLUIDO else None
        if task.status in (Task.Status.EM_PROGRESSO, Task.Status.CONCLUIDO) and task.started_at is None:
            task.started_at = agora
        task.save(update_fields=["done_at", "started_at"])
        self._evento(task, f"Moveu de “{ROTULO_STATUS[antigo]}” para “{ROTULO_STATUS[task.status]}”.")

    def perform_create(self, serializer):
        board = serializer.validated_data["board"]
        ultima = Task.objects.filter(board=board, status=serializer.validated_data.get("status", Task.Status.A_FAZER)).aggregate(m=Max("order"))["m"] or 0
        task = serializer.save(created_by=self.request.user, order=ultima + 1)
        self._evento(task, "Criou a tarefa.")

    def perform_update(self, serializer):
        antes = serializer.instance
        antigo_status, antigo_resp, antigo_prazo = antes.status, antes.responsible_id, antes.due_date
        task = serializer.save()
        self._aplicar_status(task, antigo_status)
        if task.responsible_id != antigo_resp:
            self._evento(task, f"Responsável: {nome(task.responsible) or 'ninguém'}.")
        if task.due_date != antigo_prazo:
            self._evento(task, f"Prazo: {task.due_date:%d/%m/%Y}." if task.due_date else "Prazo removido.")

    def perform_destroy(self, instance):
        if not role_at_least(self.request.user, User.Role.GESTOR):
            raise PermissionDenied("Só gestor ou administrador exclui tarefas.")
        instance.delete()

    @action(detail=True, methods=["patch"])
    def move(self, request, pk=None):
        """Arrastar no quadro: muda a coluna e/ou a posição."""
        task = self.get_object()
        novo = request.data.get("status", task.status)
        if novo not in Task.Status.values:
            raise ValidationError({"status": "Status inválido."})
        antigo = task.status
        task.status = novo
        if "order" in request.data:
            task.order = int(request.data["order"])
        task.save(update_fields=["status", "order"])
        self._aplicar_status(task, antigo)
        return Response(TaskSerializer(task, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"])
    def historico(self, request, pk=None):
        return Response(TaskEventSerializer(self.get_object().events.select_related("author"), many=True).data)

    @action(detail=True, methods=["get", "post"])
    def mensagens(self, request, pk=None):
        task = self.get_object()
        if request.method == "GET":
            qs = task.messages.select_related("sender", "recipient").prefetch_related("replies__author")
            return Response(TaskMessageSerializer(qs, many=True).data)
        ser = TaskMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        destino = ser.validated_data.get("recipient")
        if destino is None or not destino.belongs_to(task.board.tenant):
            raise ValidationError({"recipient": "Escolha para quem é a mensagem."})
        msg = ser.save(task=task, sender=request.user)
        self._evento(task, f"Enviou uma mensagem para {nome(destino)}.")
        return Response(TaskMessageSerializer(msg).data, status=201)

    @action(detail=False, methods=["get"])
    def analise(self, request):
        qs = self.get_queryset()
        if request.query_params.get("board", "").isdigit():
            qs = qs.filter(board=request.query_params["board"])
        if request.query_params.get("map", "").isdigit():
            qs = qs.filter(board__map=request.query_params["map"])
        tarefas = list(qs)
        hoje = date.today()
        abertas = [t for t in tarefas if t.status != Task.Status.CONCLUIDO]
        atrasadas = sorted((t for t in abertas if t.due_date and t.due_date < hoje), key=lambda t: t.due_date)
        por_status = Counter(t.status for t in tarefas)
        por_board = Counter(t.board.name for t in tarefas)
        resp = defaultdict(lambda: {"total": 0, "concluidas": 0, "atrasadas": 0})
        for t in tarefas:
            r = resp[nome(t.responsible) or "Sem responsável"]
            r["total"] += 1
            r["concluidas"] += int(t.status == Task.Status.CONCLUIDO)
            r["atrasadas"] += int(t in atrasadas)
        total = len(tarefas)
        return Response({
            "total": total,
            "por_status": {k: por_status.get(k, 0) for k in Task.Status.values},
            "atrasadas": len(atrasadas),
            "conclusao_pct": round(100 * por_status.get(Task.Status.CONCLUIDO, 0) / total) if total else 0,
            "por_board": [{"board": b, "total": n} for b, n in por_board.most_common()],
            "por_responsavel": [
                {"nome": n, **v, "pct": round(100 * v["concluidas"] / v["total"]) if v["total"] else 0}
                for n, v in sorted(resp.items(), key=lambda kv: -kv[1]["total"])
            ],
            "lista_atrasadas": [
                {"id": t.id, "title": t.title, "board": t.board.name, "responsible_name": nome(t.responsible),
                 "priority": t.priority, "due_date": t.due_date, "days_late": (hoje - t.due_date).days}
                for t in atrasadas[:20]
            ],
        })


class TaskMessageViewSet(_DoTenant):
    """Caixa de comunicação do Kanban. Criar mensagem é pela tarefa (/kanban-tasks/<id>/mensagens/)."""

    queryset = TaskMessage.objects.select_related("task", "sender", "recipient").prefetch_related("replies__author")
    serializer_class = TaskMessageSerializer
    tenant_path = "task__board__tenant"
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        user, p = self.request.user, self.request.query_params
        # Colaborador só vê a conversa dele; gestor vê todas, ou só as dele com ?minhas=1.
        if p.get("minhas") or not role_at_least(user, User.Role.GESTOR):
            qs = qs.filter(Q(sender=user) | Q(recipient=user))
        if p.get("status") in TaskMessage.Status.values:
            qs = qs.filter(status=p["status"])
        if p.get("board", "").isdigit():
            qs = qs.filter(task__board=p["board"])
        return qs

    def create(self, request, *args, **kwargs):
        raise ValidationError("Envie a mensagem pela tarefa.")

    def perform_destroy(self, instance):
        if instance.sender_id != self.request.user.id and not role_at_least(self.request.user, User.Role.ADMIN):
            raise PermissionDenied("Só quem enviou pode apagar a mensagem.")
        instance.delete()

    @action(detail=False, methods=["get"])
    def resumo(self, request):
        """Contadores da aba Comunicação e o selo de pendências de quem está logado."""
        qs = self.get_queryset()
        contagem = Counter(qs.values_list("status", flat=True))
        eu = request.user
        comigo = qs.filter(Q(recipient=eu, status=TaskMessage.Status.PENDENTE) | Q(sender=eu, status=TaskMessage.Status.AGUARDANDO)).count()
        return Response({"todos": sum(contagem.values()), **{k: contagem.get(k, 0) for k in TaskMessage.Status.values}, "comigo": comigo})

    @action(detail=True, methods=["post"])
    def responder(self, request, pk=None):
        msg = self.get_object()
        texto = (request.data.get("text") or "").strip()
        if not texto:
            raise ValidationError({"text": "Escreva a resposta."})
        TaskReply.objects.create(message=msg, author=request.user, text=texto)
        if msg.status != TaskMessage.Status.CONCLUIDA:
            # Quem recebeu respondeu: a bola volta para quem pediu. Se quem pediu escreve de novo, volta a ficar pendente.
            msg.status = TaskMessage.Status.PENDENTE if request.user.id == msg.sender_id else TaskMessage.Status.AGUARDANDO
        msg.save()
        return Response(TaskMessageSerializer(self.get_queryset().get(pk=msg.pk)).data)   # relê: as respostas vieram por prefetch

    @action(detail=True, methods=["post"])
    def confirmar(self, request, pk=None):
        msg = self.get_object()
        if request.user.id != msg.sender_id and not role_at_least(request.user, User.Role.ADMIN):
            raise PermissionDenied("Só quem enviou a mensagem confirma a conclusão.")
        msg.status = TaskMessage.Status.CONCLUIDA
        msg.save()
        return Response(TaskMessageSerializer(msg).data)

    @action(detail=True, methods=["post"])
    def reabrir(self, request, pk=None):
        msg = self.get_object()
        msg.status = TaskMessage.Status.PENDENTE
        msg.save()
        return Response(TaskMessageSerializer(msg).data)
