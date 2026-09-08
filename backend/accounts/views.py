from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MODULOS, SETORES, AccessProfile, OrgUnit, Tenant, User, seed_access_profiles
from .permissions import IsRoot, IsTenantAdmin
from .serializers import AccessProfileSerializer, MeSerializer, OrgUnitSerializer, TenantSerializer, UserSerializer
from .tenancy import TenantScopedViewSet, get_request_tenant


class MeView(APIView):
    def get(self, request):
        data = MeSerializer(request.user).data
        tenant = get_request_tenant(request)
        data["acting_tenant"] = TenantSerializer(tenant).data if tenant else None
        return Response(data)


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsRoot]
    # Sem DELETE: todo dado de negócio aponta para o tenant com on_delete=PROTECT,
    # então a exclusão estouraria. Desativar é a operação correta e reversível.
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        tenant = self.get_object()
        tenant.is_active = not tenant.is_active
        tenant.save(update_fields=["is_active"])
        return Response(TenantSerializer(tenant).data)

    @action(detail=True, methods=["get"])
    def armazenamento(self, request, pk=None):
        """Disco ocupado pelos dados da empresa, por tabela e no total."""
        return Response({"tenant": pk, **armazenamento_do_tenant(self.get_object())})


class UserViewSet(TenantScopedViewSet):
    queryset = User.objects.select_related("org_unit")
    serializer_class = UserSerializer
    permission_classes = [IsTenantAdmin]
    search_fields = ["first_name", "last_name", "email"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise PermissionDenied("Você não pode excluir a si mesmo.")
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class OrgUnitViewSet(TenantScopedViewSet):
    queryset = OrgUnit.objects.select_related("manager", "parent")
    serializer_class = OrgUnitSerializer
    permission_classes = [IsTenantAdmin]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    @action(detail=False, methods=["get"])
    def tree(self, request):
        units = list(self.get_queryset())
        by_parent = {}
        for u in units:
            by_parent.setdefault(u.parent_id, []).append(u)

        def build(parent_id):
            return [
                {**OrgUnitSerializer(u).data, "children": build(u.id)}
                for u in by_parent.get(parent_id, [])
            ]

        return Response(build(None))


class AccessProfileViewSet(TenantScopedViewSet):
    """Perfis de acesso por setor da empresa (admin edita; todos podem listar para escolher)."""

    queryset = AccessProfile.objects.all()
    serializer_class = AccessProfileSerializer
    permission_classes = [IsTenantAdmin]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    def perform_destroy(self, instance):
        if instance.is_system:
            raise PermissionDenied("Perfil padrão não pode ser excluído; ajuste os setores e módulos.")
        instance.users.update(access_profile=None)
        instance.delete()

    @action(detail=False, methods=["get"])
    def opcoes(self, request):
        return Response({
            "setores": [{"key": k, "label": v} for k, v in SETORES],
            "modulos": [{"key": k, "label": v} for k, v in MODULOS],
        })

    @action(detail=False, methods=["post"])
    def padrao(self, request):
        """Recria os perfis padrão que faltarem."""
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        return Response({"criados": seed_access_profiles(tenant)})


def armazenamento_do_tenant(tenant):
    """Quanto de disco os dados de uma empresa ocupam, tabela a tabela (estimativa).

    Tamanho em disco da tabela (dados + índices, pg_total_relation_size) rateado
    pela fração de linhas que pertencem à empresa. Só tabelas com coluna tenant.
    """
    from django.apps import apps
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("""SELECT relname, pg_total_relation_size(relid), greatest(n_live_tup, 1)
                       FROM pg_stat_user_tables""")
        fisico = {r[0]: (int(r[1]), int(r[2])) for r in cur.fetchall()}

    linhas = []
    for model in apps.get_models():
        campos = {f.name: f for f in model._meta.get_fields() if getattr(f, "concrete", False)}
        if "tenant" not in campos or model._meta.abstract or model._meta.proxy:
            continue
        tabela = model._meta.db_table
        tamanho, total = fisico.get(tabela, (0, 1))
        n = model.objects.filter(tenant=tenant).count()
        if n == 0:
            continue
        # A estimativa do Postgres (n_live_tup) pode estar abaixo da contagem real logo após carga grande.
        fracao = min(1.0, n / max(total, n))
        linhas.append({
            "tabela": tabela, "modelo": model._meta.verbose_name.title() if model._meta.verbose_name else model.__name__,
            "app": model._meta.app_label, "linhas": n, "bytes": int(tamanho * fracao), "tabela_bytes": tamanho,
        })
    linhas.sort(key=lambda r: -r["bytes"])
    return {"total_bytes": sum(r["bytes"] for r in linhas), "total_linhas": sum(r["linhas"] for r in linhas), "tabelas": linhas}
