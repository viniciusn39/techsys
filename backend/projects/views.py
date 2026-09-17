from django.db.models import Max
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.permissions import IsGestorOrAbove
from accounts.tenancy import TenantScopedViewSet, get_request_tenant

from .models import ActivityFca, Andamento, Project, ProjectActivity
from .serializers import ActivityFcaSerializer, ProjectActivitySerializer, ProjectSerializer
from .services import arvores_por_projeto, calcular_arvore, painel, resumo_projeto


class ProjectViewSet(TenantScopedViewSet):
    queryset = Project.objects.select_related("owner", "org_unit", "map").prefetch_related(
        "partners", "swot_items", "objectives"
    )
    serializer_class = ProjectSerializer
    permission_classes = [IsGestorOrAbove]
    filterset_fields = ["status", "owner", "org_unit", "map", "objectives", "swot_items"]
    search_fields = ["title", "description"]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    def _com_resumos(self, projects, many):
        ctx = self.get_serializer_context()
        lista = list(projects) if many else [projects]
        ctx["resumos"] = {pid: resumo_projeto(l) for pid, l in arvores_por_projeto(lista).items()}
        return ProjectSerializer(lista if many else projects, many=many, context=ctx).data

    def list(self, request, *args, **kwargs):
        return Response(self._com_resumos(self.filter_queryset(self.get_queryset()), many=True))

    def retrieve(self, request, *args, **kwargs):
        return Response(self._com_resumos(self.get_object(), many=False))

    def perform_create(self, serializer):
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        ultimo = Project.objects.filter(tenant=tenant).aggregate(m=Max("code"))["m"] or 0
        extra = {}
        if "map" not in serializer.validated_data:
            from strategy.current import mapa_atual

            extra["map"] = mapa_atual(self.request, tenant)
        serializer.save(tenant=tenant, code=ultimo + 1, **extra)

    @action(detail=True, methods=["get"])
    def atividades(self, request, pk=None):
        """EAP do projeto já em ordem, com numeração, nível, avanço efetivo e atraso."""
        project = self.get_object()
        linhas = calcular_arvore(list(project.activities.select_related("responsible")))
        fcas = {}
        for f in ActivityFca.objects.filter(activity__project=project).values_list("activity_id", flat=True):
            fcas[f] = fcas.get(f, 0) + 1
        saida = []
        for l in linhas:
            d = ProjectActivitySerializer(l["obj"]).data
            d.update(wbs=l["wbs"], depth=l["depth"], has_children=l["has_children"], progress=l["progress"],
                     late=l["late"], fcas_count=fcas.get(l["obj"].id, 0))
            saida.append(d)
        return Response(saida)

    @action(detail=True, methods=["get"])
    def fcas(self, request, pk=None):
        """Todos os FCAs do projeto, de todas as atividades."""
        qs = ActivityFca.objects.filter(activity__project=self.get_object()).select_related("activity", "responsible")
        return Response(ActivityFcaSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Painel consolidado. Filtros: ?map=, ?project=, ?objective=."""
        qs = self.get_queryset()
        if request.query_params.get("map"):
            qs = qs.filter(map_id=request.query_params["map"])
        if request.query_params.get("project"):
            qs = qs.filter(id=request.query_params["project"])
        if request.query_params.get("objective"):
            qs = qs.filter(objectives=request.query_params["objective"])
        return Response(painel(list(qs.distinct())))


class _DoProjeto(viewsets.ModelViewSet):
    """Base dos filhos do projeto: o tenant vem do projeto, não da própria linha."""

    permission_classes = [IsGestorOrAbove]
    pagination_class = None
    tenant_path = "project__tenant"

    def get_queryset(self):
        tenant = get_request_tenant(self.request)
        if tenant is None:
            return self.queryset.none()
        return self.queryset.filter(**{self.tenant_path: tenant})


class ProjectActivityViewSet(_DoProjeto):
    queryset = ProjectActivity.objects.select_related("project", "responsible", "parent")
    serializer_class = ProjectActivitySerializer
    filterset_fields = ["project", "status", "phase", "responsible"]

    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request)
        project = serializer.validated_data["project"]
        if tenant is None or project.tenant_id != tenant.id:
            raise PermissionDenied("Projeto de outra empresa.")
        irmas = ProjectActivity.objects.filter(project=project, parent=serializer.validated_data.get("parent"))
        ordem = (irmas.aggregate(m=Max("order"))["m"] or 0) + 1
        self._salvar(serializer, order=ordem)

    def perform_update(self, serializer):
        self._salvar(serializer)

    def _salvar(self, serializer, **extra):
        """Status e % andam juntos: finalizada = 100%; 100% finaliza; sair de 0% inicia."""
        dados = serializer.validated_data
        atual = serializer.instance
        status = dados.get("status", atual.status if atual else Andamento.NAO_INICIADO)
        pct = dados.get("progress_pct", atual.progress_pct if atual else 0)
        if status == Andamento.FINALIZADO:
            pct = 100
        elif pct >= 100 and "progress_pct" in dados:
            status = Andamento.FINALIZADO
        elif pct > 0 and status == Andamento.NAO_INICIADO:
            status = Andamento.EM_ANDAMENTO
        done_at = atual.done_at if atual else None
        if status == Andamento.FINALIZADO:
            done_at = done_at or timezone.now()
        else:
            done_at = None
        item = serializer.save(status=status, progress_pct=pct, done_at=done_at, **extra)
        # Projeto parado começa a andar quando a primeira atividade anda.
        projeto = item.project
        if projeto.status == Andamento.NAO_INICIADO and status in (Andamento.EM_ANDAMENTO, Andamento.FINALIZADO):
            projeto.status = Andamento.EM_ANDAMENTO
            projeto.save(update_fields=["status"])


class ActivityFcaViewSet(_DoProjeto):
    queryset = ActivityFca.objects.select_related("activity", "responsible")
    serializer_class = ActivityFcaSerializer
    filterset_fields = ["activity", "status"]
    tenant_path = "activity__project__tenant"

    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request)
        if tenant is None or serializer.validated_data["activity"].project.tenant_id != tenant.id:
            raise PermissionDenied("Atividade de outra empresa.")
        serializer.save()
